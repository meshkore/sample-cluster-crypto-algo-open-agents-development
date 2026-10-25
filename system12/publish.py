"""Build the System 12 page (status tiles, year table, paper curve) and the architecture page, then publish.

    python -m system12.publish             # build into SITE_DIR (index.html, architecture.html, architecture.txt)
    python -m system12.publish --deploy    # also upload one Cloudflare Worker serving both pages

The Worker is uploaded under every name in WORKERS so the existing public URLs keep working. Credentials come from
~/.cf_deploy_env (outside the repository) and are never printed.
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import data, paper
from . import strategy as S

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = data.DATA_DIR.parent / "site"
WORKERS = ("quantlab-public-mirror", "quantlab-architecture")
API = "https://api.cloudflare.com/client/v4"
REPO = "https://github.com/meshkore/sample-cluster-crypto-algo-open-agents-development"


# ------------------------------------------------------------------ numbers


def year_table(w) -> dict:
    rec = json.loads((Path(__file__).with_name("record.json")).read_text(encoding="utf-8"))
    ours = {int(y): v for y, v in rec["years"].items()}
    W = S.weights(w)
    yr = w.p4["year"]
    rows = np.flatnonzero(yr == 2026)
    if len(rows):
        Wp = np.zeros_like(W)
        Wp[rows] = W[rows]
        eq = np.cumprod(1 + S.bar_returns(w, Wp)[rows])
        ours[2026] = {"ret": float(eq[-1] - 1), "dd": float((1 - eq / np.maximum.accumulate(eq)).max())}
    btc, c4 = {}, w.p4["close"][:, 0]
    for y in ours:
        sel = np.flatnonzero((yr == y) & np.isfinite(c4))
        prev = np.flatnonzero((yr == y - 1) & np.isfinite(c4))
        if len(sel) and len(prev):
            btc[y] = float(c4[sel[-1]] / c4[prev[-1]] - 1)
    return {"years": sorted(ours), "ours": ours, "btc": btc}


# ------------------------------------------------------------------ pages

CSS = """:root{--bg:#f7f7f4;--fg:#1b1b19;--mut:#6a6a63;--line:#deded6;--card:#fff;--up:#1a7f4b;--dn:#b3261e;--acc:#1f5fbf}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111110;--fg:#ebebe5;--mut:#9d9d95;--line:#30302c;--card:#1a1a18;--up:#5cc58c;--dn:#ff8a80;--acc:#7fb0ff}}
:root[data-theme="dark"]{--bg:#111110;--fg:#ebebe5;--mut:#9d9d95;--line:#30302c;--card:#1a1a18;--up:#5cc58c;--dn:#ff8a80;--acc:#7fb0ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:960px;margin:0 auto;padding:20px 16px 56px}
header{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:16px}
h1{font-size:1.3rem;margin:0}h2{font-size:1rem;margin:28px 0 10px}.mut{color:var(--mut);font-size:.85rem}
nav a{color:var(--acc);text-decoration:none;margin-left:14px;font-size:.9rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile b{display:block;font-size:1.35rem;font-variant-numeric:tabular-nums}.tile span{color:var(--mut);font-size:.82rem}
.up{color:var(--up)}.dn{color:var(--dn)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:7px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}th:first-child,td:first-child{text-align:left}
svg{display:block;width:100%;height:auto}
.doc h1{font-size:1.4rem}.doc h2{border-top:1px solid var(--line);padding-top:14px}.doc table{margin:8px 0 16px}
.doc th,.doc td{text-align:left;white-space:normal}.doc li{margin:3px 0}"""


def _pct(x, digits=1, sign=True) -> str:
    if x is None or not np.isfinite(x):
        return "-"
    cls = "up" if x > 0 else "dn" if x < 0 else ""
    return f'<span class="{cls}">{x * 100:{"+" if sign else ""}.{digits}f}%</span>'


def _chart(curve: list) -> str:
    if len(curve) < 2:
        return '<p class="mut">The curve starts after the first closed 4h bar.</p>'
    v = np.array([c[1] for c in curve])
    lo, hi = min(v.min(), 1.0), max(v.max(), 1.0)
    pad = (hi - lo) * 0.1 or 0.01
    lo, hi = lo - pad, hi + pad
    X = np.linspace(0, 900, len(v))
    Y = 200 - (v - lo) / (hi - lo) * 200
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(X, Y))
    y1 = 200 - (1 - lo) / (hi - lo) * 200
    return (
        f'<svg viewBox="0 0 900 200" role="img" aria-label="paper equity"><line x1="0" x2="900" y1="{y1:.1f}" '
        f'y2="{y1:.1f}" stroke="var(--line)" stroke-dasharray="4 4"/><polyline fill="none" stroke="var(--acc)" '
        f'stroke-width="2" points="{pts}"/></svg><p class="mut">{curve[0][0]} to {curve[-1][0]} UTC, 4h bars</p>'
    )


def dashboard(state: dict, yt: dict) -> str:
    tgt = state.get("target", {})
    pos = " / ".join(f"{k} {v * 100:+.0f}%" for k, v in tgt.items()) or "flat"
    net = state.get("net_exposure", 0.0)
    phase = "long" if net > 0.01 else "short" if net < -0.01 else "flat"
    tiles = [
        (f"${state.get('equity_usd', state['book_usd']):,.0f}", f"paper book, from ${state['book_usd']:,.0f}"),
        (_pct(state.get("ret", 0.0), 2), f"since {state['start']} UTC"),
        (_pct(-state.get("max_dd", 0.0), 2), "max drawdown"),
        (f"{net * 100:+.0f}%", f"net exposure ({phase})"),
        (pos, "target position"),
        (f"${state.get('btc', 0):,.0f}", f"BTC at {state['as_of_bar']} UTC"),
    ]
    t = "".join(f'<div class="tile"><b>{a}</b><span>{html.escape(b)}</span></div>' for a, b in tiles)
    ys = yt["years"]
    head = "".join(f"<th>{y}{' YTD' if y == 2026 else ''}</th>" for y in ys)
    ours = "".join(f"<td>{_pct(yt['ours'][y]['ret'], 0)}</td>" for y in ys)
    dd = "".join(f"<td class=mut>{yt['ours'][y]['dd'] * 100:.0f}%</td>" for y in ys)
    btc = "".join(f"<td>{_pct(yt['btc'].get(y), 0)}</td>" for y in ys)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>System 12 Live</title><style>{CSS}</style></head><body><main>
<header><div><h1>System 12 · BTC regime</h1><div class="mut">paper trading · updated {state["updated"][:16].replace("T", " ")} UTC · every 4h</div></div>
<nav><a href="/architecture">Architecture</a><a href="{REPO}">Code</a></nav></header>
<div class="tiles">{t}</div>
<h2>Year by year</h2><div class="card tw"><table><thead><tr><th></th>{head}</tr></thead><tbody>
<tr><td><b>System 12</b></td>{ours}</tr><tr><td class=mut>max drawdown</td>{dd}</tr><tr><td>BTC</td>{btc}</tr></tbody></table></div>
<p class="mut">2021-2025 walk-forward: each year traded with rules chosen on earlier years only. 2026 is out of sample.</p>
<h2>Paper book</h2><div class="card">{_chart(state.get("curve", []))}</div>
</main></body></html>"""


def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def md_to_html(md: str) -> str:
    """The Markdown subset docs/ARCHITECTURE.md uses: headings, paragraphs, flat lists, pipe tables, bold, code."""
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
        elif ln.startswith("#"):
            n = len(ln) - len(ln.lstrip("#"))
            out.append(f"<h{n}>{_inline(ln[n:].strip())}</h{n}>")
            i += 1
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            head = "".join(f"<th>{_inline(c)}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
        elif re.match(r"\s*(- |\d+\. )", ln):
            items = []
            while i < len(lines) and re.match(r"\s*(- |\d+\. )", lines[i]):
                items.append(re.sub(r"^\s*(- |\d+\. )", "", lines[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ul>")
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"(#|\||\s*- |\s*\d+\. )", lines[i]):
                para.append(lines[i])
                i += 1
            out.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(out)


def architecture(md: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>System 12 Architecture</title><style>{CSS}</style></head><body><main class="doc">
<header><div class="mut">System 12</div><nav><a href="/">Live</a><a href="/architecture.txt">Plain text</a><a href="{REPO}">Code</a></nav></header>
{md_to_html(md)}</main></body></html>"""


WORKER = """const PAGES = __PAGES__;
export default {
  async fetch(req) {
    let p = new URL(req.url).pathname.replace(/\\/+$/, "") || "/";
    if (p === "/live") p = "/";
    const page = PAGES[p];
    if (!page) return new Response("not found", {status: 404});
    return new Response(page[1], {headers: {"content-type": page[0], "cache-control": "public, max-age=120"}});
  }
};
"""


def build() -> dict:
    w = S.world()
    state = paper.run(w)
    md = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    pages = {
        "/": ["text/html; charset=utf-8", dashboard(state, year_table(w))],
        "/architecture": ["text/html; charset=utf-8", architecture(md)],
        "/architecture.txt": ["text/plain; charset=utf-8", md],
    }
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "index.html").write_text(pages["/"][1], encoding="utf-8")
    (SITE_DIR / "architecture.html").write_text(pages["/architecture"][1], encoding="utf-8")
    (SITE_DIR / "architecture.txt").write_text(md, encoding="utf-8")
    return pages


def _env() -> dict:
    out = {}
    for line in (Path.home() / ".cf_deploy_env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _call(method: str, url: str, token: str, body: bytes, ctype: str) -> None:
    req = urllib.request.Request(
        url, data=body, method=method, headers={"Authorization": f"Bearer {token}", "Content-Type": ctype}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            r.read()
    except urllib.error.HTTPError as e:
        errs = json.loads(e.read().decode("utf-8", "replace") or "{}").get("errors", [])
        raise SystemExit(f"{method} failed ({e.code}): " + "; ".join(f"[{x.get('code')}] {x.get('message')}" for x in errs))


def deploy(pages: dict) -> None:
    e = _env()
    token, acct, sub = e["CLOUDFLARE_API_TOKEN"], e["CLOUDFLARE_ACCOUNT_ID"], e.get("WORKERS_SUBDOMAIN", "")
    src = WORKER.replace("__PAGES__", json.dumps(pages))
    for name in WORKERS:
        b = "----system12" + uuid.uuid4().hex
        meta = json.dumps({"main_module": "worker.js", "compatibility_date": "2024-11-01"})
        body = (
            f'--{b}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n{meta}\r\n'
            f'--{b}\r\nContent-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
            f"Content-Type: application/javascript+module\r\n\r\n{src}\r\n--{b}--\r\n"
        ).encode("utf-8")
        _call("PUT", f"{API}/accounts/{acct}/workers/scripts/{name}", token, body, f"multipart/form-data; boundary={b}")
        _call(
            "POST",
            f"{API}/accounts/{acct}/workers/scripts/{name}/subdomain",
            token,
            json.dumps({"enabled": True, "previews_enabled": False}).encode(),
            "application/json",
        )
        print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M}] deployed https://{name}.{sub}.workers.dev", flush=True)


def main() -> int:
    pages = build()
    print(f"built {SITE_DIR}", flush=True)
    if "--deploy" in sys.argv:
        deploy(pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
