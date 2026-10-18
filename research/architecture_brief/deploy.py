"""Publish brief.md as a public, read-only page on its own Cloudflare Worker (REST API, no Node).

    /architecture      the brief as a page (with a copy button)
    /architecture.txt  the same text, plain, for language models
    /                  redirects to /architecture

Its own Worker (quantlab-architecture), so the live mirror is never touched. Credentials come
from ~/.cf_deploy_env (outside the repo), never printed.

    python research/architecture_brief/deploy.py           # build + deploy
    python research/architecture_brief/deploy.py --build    # write worker.js only
"""

from __future__ import annotations

import html
import json
import re
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "research/system06/preview"))
NAME = "quantlab-architecture"


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def to_html(md: str) -> str:
    """The small Markdown subset brief.md uses: #/## headings, paragraphs, nested - and 1. lists,
    pipe tables, **bold**."""
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
        elif ln.startswith("# "):
            out.append(f"<h1>{inline(ln[2:])}</h1>"); i += 1
        elif ln.startswith("## "):
            out.append(f"<h2>{inline(ln[3:])}</h2>"); i += 1
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"-+", c) for c in cells):
                    rows.append(cells)
                i += 1
            head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
        elif re.match(r"\s*(- |\d+\. )", ln):
            items = []
            while i < len(lines) and re.match(r"\s*(- |\d+\. )", lines[i]):
                m = re.match(r"(\s*)(- |\d+\. )(.*)", lines[i])
                items.append((len(m.group(1)), m.group(2) != "- ", m.group(3)))
                i += 1
            out.append(render_list(items))
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"(#|\||\s*- |\s*\d+\. )", lines[i]):
                para.append(lines[i]); i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)


def render_list(items: list[tuple[int, bool, str]]) -> str:
    """Nested list from (indent, ordered, text) rows."""
    html_, stack = [], []
    for ind, ordered, text in items:
        while stack and stack[-1][0] > ind:
            html_.append(f"</li></{stack.pop()[1]}>")
        if stack and stack[-1][0] == ind:
            html_.append("</li>")
        elif not stack or stack[-1][0] < ind:
            tag = "ol" if ordered else "ul"
            stack.append((ind, tag))
            html_.append(f"<{tag}>")
        html_.append(f"<li>{inline(text)}")
    while stack:
        html_.append(f"</li></{stack.pop()[1]}>")
    return "".join(html_)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantLab Architecture Brief</title>
<meta name="description" content="Request for an independent expert review of a crypto trading research program.">
<style>
:root{--bg:#fbfbf9;--fg:#1c1c1a;--mut:#62625c;--line:#dcdcd4;--acc:#1f5fbf;--card:#fff}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121211;--fg:#e8e8e2;--mut:#a0a098;--line:#33332f;--acc:#7fb0ff;--card:#1a1a18}}
:root[data-theme="dark"]{--bg:#121211;--fg:#e8e8e2;--mut:#a0a098;--line:#33332f;--acc:#7fb0ff;--card:#1a1a18}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.6rem;line-height:1.25;margin:0 0 12px}h2{font-size:1.15rem;margin:32px 0 8px;padding-top:12px;border-top:1px solid var(--line)}
p,li{color:var(--fg)}ul,ol{padding-left:22px}li{margin:4px 0}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 20px}
.bar a,.bar button{font:inherit;font-size:.9rem;padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--acc);text-decoration:none;cursor:pointer}
.note{color:var(--mut);font-size:.9rem;margin:0 0 20px}
.tw{overflow-x:auto;margin:8px 0 16px}table{border-collapse:collapse;font-size:.92rem;min-width:100%}
th,td{border:1px solid var(--line);padding:6px 10px;text-align:left;white-space:nowrap}th{background:var(--card)}
</style></head><body><main>
<div class="bar"><button id="copy">Copy prompt</button><a href="/architecture.txt">Plain text</a></div>
<p class="note">Paste this page, or its plain-text version, into any language model as a prompt. Figures as of __DATE__.</p>
__BODY__
</main><script>
const T=__TEXT__;
document.getElementById("copy").onclick=async e=>{try{await navigator.clipboard.writeText(T);e.target.textContent="Copied"}catch(_){e.target.textContent="Copy failed"}};
</script></body></html>"""

WORKER = """const TEXT = __TEXT__;
const PAGE = __PAGE__;
export default {
  async fetch(req) {
    const p = new URL(req.url).pathname.replace(/\\/+$/, "");
    const h = {"cache-control": "public, max-age=300", "x-robots-tag": "noindex"};
    if (p === "/architecture.txt") return new Response(TEXT, {headers: {...h, "content-type": "text/plain; charset=utf-8"}});
    if (p === "/architecture") return new Response(PAGE, {headers: {...h, "content-type": "text/html; charset=utf-8"}});
    if (p === "") return Response.redirect(new URL("/architecture", req.url).toString(), 302);
    return new Response("not found", {status: 404});
  }
};
"""


def build() -> str:
    md = (HERE / "brief.md").read_text(encoding="utf-8")
    date = (HERE / "AS_OF").read_text(encoding="utf-8").strip() if (HERE / "AS_OF").exists() else ""
    page = PAGE.replace("__DATE__", html.escape(date)).replace("__BODY__", to_html(md)).replace("__TEXT__", json.dumps(md))
    src = WORKER.replace("__TEXT__", json.dumps(md)).replace("__PAGE__", json.dumps(page))
    (HERE / "worker.js").write_text(src, encoding="utf-8")
    return src


def deploy(src: str) -> None:
    import cf_deploy as C
    e = C.env()
    token, acct = e["CLOUDFLARE_API_TOKEN"], e["CLOUDFLARE_ACCOUNT_ID"]
    boundary = "----brief" + uuid.uuid4().hex
    meta = json.dumps({"main_module": "worker.js", "compatibility_date": "2024-11-01"})
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n{meta}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
            f"Content-Type: application/javascript+module\r\n\r\n{src}\r\n--{boundary}--\r\n").encode("utf-8")
    C.call("PUT", f"{C.API}/accounts/{acct}/workers/scripts/{NAME}", token, body, f"multipart/form-data; boundary={boundary}")
    C.call("POST", f"{C.API}/accounts/{acct}/workers/scripts/{NAME}/subdomain", token,
           json.dumps({"enabled": True, "previews_enabled": False}).encode(), "application/json")
    sub = e.get("WORKERS_SUBDOMAIN", "")
    print(f"  deployed https://{NAME}.{sub}.workers.dev/architecture" if sub else f"  deployed {NAME}")


if __name__ == "__main__":
    s = build()
    if "--build" not in sys.argv:
        deploy(s)
