"""HTML for the two public pages: the live view (status tiles, year table, paper curve) and the architecture brief."""

from __future__ import annotations

import html
import re

import numpy as np

REPO_URL = "https://github.com/meshkore/sample-cluster-crypto-algo-open-agents-development"

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

HEAD = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'


def pct(x: float | None, digits: int = 1) -> str:
    if x is None or not np.isfinite(x):
        return "-"
    cls = "up" if x > 0 else "dn" if x < 0 else ""
    return f'<span class="{cls}">{x * 100:+.{digits}f}%</span>'


def chart(curve: list) -> str:
    if len(curve) < 2:
        return '<p class="mut">The curve starts after the first closed 4h bar.</p>'
    v = np.array([c[1] for c in curve])
    lo, hi = min(v.min(), 1.0), max(v.max(), 1.0)
    pad = (hi - lo) * 0.1 or 0.01
    lo, hi = lo - pad, hi + pad
    y = 200 - (v - lo) / (hi - lo) * 200
    pts = " ".join(f"{x:.1f},{yy:.1f}" for x, yy in zip(np.linspace(0, 900, len(v)), y))
    base = 200 - (1 - lo) / (hi - lo) * 200
    return (
        f'<svg viewBox="0 0 900 200" role="img" aria-label="paper equity">'
        f'<line x1="0" x2="900" y1="{base:.1f}" y2="{base:.1f}" stroke="var(--line)" stroke-dasharray="4 4"/>'
        f'<polyline fill="none" stroke="var(--acc)" stroke-width="2" points="{pts}"/></svg>'
        f'<p class="mut">{curve[0][0]} to {curve[-1][0]} UTC, 4h bars</p>'
    )


def live(state: dict, years: dict) -> str:
    """`years`: {year: (return, max drawdown, BTC return)}; the last year is shown as year to date."""
    target = " / ".join(f"{k} {v * 100:+.0f}%" for k, v in state["target"].items()) or "flat"
    net = state["net_exposure"]
    side = "long" if net > 0.01 else "short" if net < -0.01 else "flat"
    tiles = [
        (f"${state['equity_usd']:,.0f}", f"paper book, from ${state['book_usd']:,.0f}"),
        (pct(state["ret"], 2), f"since {state['start']} UTC"),
        (pct(-state["max_dd"], 2), "max drawdown"),
        (f"{net * 100:+.0f}%", f"net exposure ({side})"),
        (target, "target position"),
        (f"${state['btc']:,.0f}", f"BTC at {state['as_of_bar']} UTC"),
    ]
    tiles_html = "".join(f'<div class="tile"><b>{a}</b><span>{html.escape(b)}</span></div>' for a, b in tiles)
    ys = sorted(years)
    head = "".join(f"<th>{y}{' YTD' if y == ys[-1] else ''}</th>" for y in ys)
    ours = "".join(f"<td>{pct(years[y][0], 0)}</td>" for y in ys)
    dd = "".join(f'<td class="mut">{years[y][1] * 100:.0f}%</td>' for y in ys)
    btc = "".join(f"<td>{pct(years[y][2], 0)}</td>" for y in ys)
    updated = state["updated"][:16].replace("T", " ")
    return f"""{HEAD}<title>System 12 Live</title><style>{CSS}</style></head><body><main>
<header><div><h1>System 12 · BTC regime</h1><div class="mut">paper trading · updated {updated} UTC · every 4h</div></div>
<nav><a href="/architecture">Architecture</a><a href="{REPO_URL}">Code</a></nav></header>
<div class="tiles">{tiles_html}</div>
<h2>Year by year</h2><div class="card tw"><table><thead><tr><th></th>{head}</tr></thead><tbody>
<tr><td><b>System 12</b></td>{ours}</tr><tr><td class="mut">max drawdown</td>{dd}</tr><tr><td>BTC</td>{btc}</tr></tbody></table></div>
<p class="mut">Walk-forward: each year traded with rules chosen on earlier years only. {ys[-1]} is out of sample.</p>
<h2>Paper book</h2><div class="card">{chart(state["curve"])}</div>
</main></body></html>"""


def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


LIST_ITEM = re.compile(r"\s*(- |\d+\. )")


def markdown(md: str) -> str:
    """The Markdown subset the docs use: headings, paragraphs, flat lists, pipe tables, bold and inline code."""
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
        elif LIST_ITEM.match(ln):
            tag = "ol" if ln.strip()[0].isdigit() else "ul"
            items = []
            while i < len(lines) and LIST_ITEM.match(lines[i]):
                items.append(LIST_ITEM.sub("", lines[i], count=1))
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"#|\||\s*- |\s*\d+\. ", lines[i]):
                para.append(lines[i])
                i += 1
            out.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(out)


def architecture(md: str) -> str:
    return f"""{HEAD}<title>System 12 Architecture</title><style>{CSS}</style></head><body><main class="doc">
<header><div class="mut">System 12</div><nav><a href="/">Live</a><a href="/architecture.txt">Plain text</a><a href="{REPO_URL}">Code</a></nav></header>
{markdown(md)}</main></body></html>"""
