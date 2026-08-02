const STATE_KEY = "latest.json";
const MAX_BODY_BYTES = 5 * 1024 * 1024;
const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

const reply = (value, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: JSON_HEADERS });
const allowed = (request, env) =>
  Boolean(env.PUBLISH_TOKEN) &&
  request.headers.get("authorization") === `Bearer ${env.PUBLISH_TOKEN}`;

async function ingest(request, env) {
  if (!allowed(request, env)) return reply({ error: "unauthorized" }, 401);
  if (Number(request.headers.get("content-length") || 0) > MAX_BODY_BYTES) {
    return reply({ error: "payload_too_large" }, 413);
  }
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return reply({ error: "payload_too_large" }, 413);
  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    return reply({ error: "invalid_json" }, 400);
  }
  if (payload?.version !== 1 || !payload?.state || typeof payload.state !== "object") {
    return reply({ error: "invalid_payload" }, 400);
  }
  const state = {
    ...payload.state,
    mirror: {
      edge_received_at: new Date().toISOString(),
      source_published_at: payload.published_at || null,
    },
  };
  await env.STATE_BUCKET.put(STATE_KEY, JSON.stringify(state), {
    httpMetadata: { contentType: "application/json" },
  });
  return reply({ ok: true, edge_received_at: state.mirror.edge_received_at });
}

async function latest(env) {
  const object = await env.STATE_BUCKET.get(STATE_KEY);
  if (!object) return reply({ status: "waiting_for_local_runner", mirror: { edge_received_at: null } });
  return new Response(await object.text(), { headers: JSON_HEADERS });
}

const PAGE = String.raw`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="A public observatory for local, long-only strategy research."><meta property="og:title" content="QuantLab · Build the signal. Show the evidence."><meta property="og:description" content="Open agent research · long-only · forward locked."><meta property="og:image" content="/og.png"><meta name="twitter:card" content="summary_large_image"><title>QuantLab · Live research observatory</title><style>
:root{color-scheme:dark;--ink:#06070a;--panel:#10111a;--line:#292c42;--text:#f5f3ff;--muted:#a6a7bb;--violet:#a78bfa;--pink:#f472b6;--coral:#fb7185;--cyan:#22d3ee;--lime:#b6ff5c;--amber:#fbbf24}*{box-sizing:border-box}body{margin:0;background:radial-gradient(900px 420px at 9% -12%,#6d28d940,transparent 70%),radial-gradient(700px 420px at 96% 0,#ec489935,transparent 68%),var(--ink);color:var(--text);font:14px ui-monospace,SFMono-Regular,Menlo,monospace}body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.16;background-image:linear-gradient(#ffffff08 1px,transparent 1px),linear-gradient(90deg,#ffffff08 1px,transparent 1px);background-size:48px 48px}main{position:relative;max-width:1540px;margin:auto;padding:28px 22px 80px}header{border-bottom:1px solid var(--line);padding-bottom:22px}.top{display:flex;justify-content:space-between;gap:30px}.kicker{color:var(--cyan);font-weight:800;font-size:11px;letter-spacing:.17em}.brand h1{font:800 clamp(34px,5vw,61px)/.94 system-ui;letter-spacing:-.06em;margin:8px 0 12px;background:linear-gradient(100deg,#fff,#ddd6fe 29%,#f0abfc 58%,#fda4af 78%,#fde68a);-webkit-background-clip:text;background-clip:text;color:transparent}.lead{max-width:690px;color:var(--muted);line-height:1.55;margin:0}.status{align-self:flex-start;min-width:215px;border:1px solid #ffffff20;border-radius:12px;background:#0d0e16cc;padding:11px 13px;color:var(--lime);font-weight:700}.status small{display:block;font-weight:400;color:var(--muted);margin-top:6px}.stale{color:var(--amber)}.offline{color:var(--coral)}.links{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}.links a{color:var(--text);text-decoration:none;border:1px solid #ffffff25;background:#ffffff08;border-radius:99px;padding:8px 12px}.links a:hover{border-color:var(--cyan);color:var(--cyan)}.notice{border:1px solid #783f1e;border-radius:13px;padding:13px 16px;margin:16px 0;background:#261708cc;color:#fde68a}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px;margin-top:16px}.card{grid-column:span 3;background:linear-gradient(145deg,#1a1c2db8,#0d0e15d9);border:1px solid var(--line);border-radius:15px;padding:17px;min-width:0;box-shadow:0 16px 40px #0003}.half{grid-column:span 6}.full{grid-column:1/-1}.metric{font:780 26px system-ui;letter-spacing:-.04em;margin-top:7px}.label,.muted{color:var(--muted)}.good{color:var(--lime)}.bad{color:var(--coral)}h2{font:720 16px system-ui;margin:0 0 14px}.table{overflow:auto;max-height:460px;border:1px solid var(--line);border-radius:10px}table{width:100%;border-collapse:collapse;white-space:nowrap}th,td{padding:10px 12px;text-align:right;border-bottom:1px solid var(--line)}th{position:sticky;top:0;background:#1a1c2d;color:var(--muted);font-weight:600}th:first-child,td:first-child{text-align:left}pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;color:#d8d7ee;font-size:12px;max-height:270px;overflow:auto}canvas{width:100%;height:210px;border-radius:10px;background:linear-gradient(180deg,#a78bfa0c,transparent)}.empty{padding:40px;text-align:center;color:var(--muted)}footer{color:var(--muted);margin-top:20px;line-height:1.6}@media(max-width:900px){.top{display:block}.status{display:inline-block;margin-top:18px}.card,.half{grid-column:span 6}}@media(max-width:600px){main{padding:20px 13px 55px}.card,.half{grid-column:1/-1}}
</style></head><body><main><header><div class="top"><div class="brand"><div class="kicker">OPEN AGENT RESEARCH · LONG-ONLY · FORWARD LOCKED</div><h1>Build the signal.<br>Show the evidence.</h1><p class="lead">A public observatory for the hypotheses, execution rules, and forward evidence produced by the local QuantLab runner.</p></div><div id="freshness" class="status">● waiting for local state<small>No update received yet</small></div></div><nav class="links"><a id="repo" href="#">Source code ↗</a><a id="cluster" href="#">Public agent cluster ↗</a><a href="/api/state">Raw public state ↗</a></nav></header><div id="notice"></div><section id="app" class="grid"><article class="card full"><div class="empty">Waiting for the first signed update from the local runner.</div></article></section><footer>Research software only, never investment advice. Historical results are not forward results. The local computer calculates; this page only presents the latest published, public-safe state.</footer></main><script>
let state;const $=id=>document.getElementById(id),money=v=>v==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(v),pct=v=>v==null?'—':(Number(v)*100).toFixed(2)+'%',num=v=>v==null?'—':new Intl.NumberFormat('en-US').format(v),date=v=>v?new Date(v).toLocaleString('en-US'):'—',cls=v=>v>0?'good':v<0?'bad':'';const card=(l,v,c='')=>'<article class="card"><div class="label">'+l+'</div><div class="metric '+c+'">'+v+'</div></article>';function esc(v){return String(v).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}function freshness(){const edge=state?.mirror?.edge_received_at;if(!edge)return;const age=(Date.now()-Date.parse(edge))/1000,el=$('freshness'),label=age>60?'● local runner offline or stopped':age>15?'● update delayed':'● live local research';el.className='status '+(age>60?'offline':age>15?'stale':'');el.innerHTML=label+'<small>Last edge update: '+date(edge)+'</small>'}function chart(points){setTimeout(()=>{const c=$('equity');if(!c||!points?.length)return;const w=c.clientWidth,h=c.clientHeight,d=devicePixelRatio||1;c.width=w*d;c.height=h*d;const x=c.getContext('2d');x.scale(d,d);const a=points.map(p=>p.equity),lo=Math.min(...a),hi=Math.max(...a),r=hi-lo||1,g=x.createLinearGradient(0,0,w,0);g.addColorStop(0,'#22d3ee');g.addColorStop(.5,'#a78bfa');g.addColorStop(1,'#f472b6');x.strokeStyle=g;x.shadowColor='#a78bfa';x.shadowBlur=12;x.lineWidth=2.5;x.beginPath();a.forEach((v,i)=>{const px=i/(a.length-1||1)*w,py=h-10-(v-lo)/r*(h-20);i?x.lineTo(px,py):x.moveTo(px,py)});x.stroke()},0)}function render(){const p=state.project||{};$('repo').href=p.repository_url||'#';$('cluster').href=p.cluster_url||'#';freshness();const s=state.current_strategy||state.best_strategy,r=s?.backtest||{},a=state.activity||{},tr=s?.trades||[],assets=s?.assets||[];$('notice').innerHTML=state.warning?'<div class="notice">'+esc(state.warning)+'</div>':'';$('app').innerHTML=card('Research state',state.loop?.state||'—')+card('Current strategy',s?.label||'—')+card('Current equity',money(r.current_equity),cls((r.current_equity||0)-(r.initial_capital||0)))+card('Net P&L',money(r.net_profit),cls(r.net_profit))+card('Maximum drawdown',pct(r.max_drawdown),'bad')+card('Trades',num(r.trades))+card('Win rate',pct(r.win_rate))+card('Data coverage',(state.data_coverage?.research_ready??'—')+'/'+(state.data_coverage?.total??'—'))+'<article class="card full"><h2>Current activity</h2><div><b>'+esc(a.phase||'WAITING')+'</b> · '+esc(a.message||'No activity published')+'</div><div class="muted" style="margin-top:8px">Local source: '+date(p.source_updated_at)+' · Public edge: '+date(state.mirror?.edge_received_at)+'</div></article>'+'<article class="card full"><h2>Portfolio equity curve</h2>'+(s?.equity_curve?.length?'<canvas id="equity"></canvas>':'<div class="empty">Equity points appear as the simulation progresses.</div>')+'</article>'+'<article class="card half"><h2>Signal criteria</h2><pre>'+esc(JSON.stringify({family:s?.definition?.family,signal:s?.definition?.signal,parameters:s?.experiment?.parameters},null,2))+'</pre></article><article class="card half"><h2>Execution and risk management</h2><pre>'+esc(JSON.stringify({execution:s?.definition?.execution,money_management:s?.definition?.money_management},null,2))+'</pre></article>'+'<article class="card full"><h2>Recent trades · '+tr.length+'</h2>'+(tr.length?'<div class="table"><table><thead><tr><th>Trade</th><th>Entry</th><th>Exit</th><th>Capital</th><th>P&amp;L</th><th>P&amp;L %</th><th>Exit reason</th></tr></thead><tbody>'+tr.map(t=>'<tr><td>'+esc(t.symbol)+' #'+t.sequence+'</td><td>'+date(t.entry_time)+'</td><td>'+date(t.exit_time)+'</td><td>'+money(t.invested_capital)+'</td><td class="'+cls(t.pnl)+'">'+money(t.pnl)+'</td><td class="'+cls(t.pnl_pct)+'">'+pct(t.pnl_pct)+'</td><td>'+esc(t.exit_reason)+'</td></tr>').join('')+'</tbody></table></div>':'<div class="empty">No trades are public yet.</div>')+'</article>'+'<article class="card full"><h2>Asset results · '+assets.length+'</h2>'+(assets.length?'<div class="table"><table><thead><tr><th>Asset</th><th>Capital</th><th>P&amp;L</th><th>Return</th><th>Trades</th><th>Win rate</th></tr></thead><tbody>'+assets.map(x=>'<tr><td>'+esc(x.symbol)+'</td><td>'+money(x.capital_deployed)+'</td><td class="'+cls(x.pnl)+'">'+money(x.pnl)+'</td><td class="'+cls(x.return_on_deployed)+'">'+pct(x.return_on_deployed)+'</td><td>'+x.trades+'</td><td>'+pct(x.win_rate)+'</td></tr>').join('')+'</tbody></table></div>':'<div class="empty">No asset results are public yet.</div>')+'</article>';chart(s?.equity_curve)}async function refresh(){try{const response=await fetch('/api/state',{cache:'no-store'});state=await response.json();if(state.status)return;render()}catch{const el=$('freshness');el.textContent='● public viewer unavailable';el.className='status offline'}}refresh();setInterval(refresh,5000);setInterval(freshness,1000);
</script></body></html>`;

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "GET, POST, OPTIONS",
          "access-control-allow-headers": "authorization, content-type",
        },
      });
    }
    const url = new URL(request.url);
    if (url.pathname === "/api/state" && request.method === "POST") return ingest(request, env);
    // `/api/dashboard` is the endpoint the local monitor's UI fetches. Serving
    // the same path here lets this Worker host that exact page unmodified, so
    // the public view can never drift from the one on the operator's machine.
    if ((url.pathname === "/api/state" || url.pathname === "/api/dashboard") && request.method === "GET") {
      return latest(env);
    }
    if (request.method === "GET") {
      if (url.pathname === "/legacy") {
        return new Response(PAGE, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
      }
      const asset = await env.ASSETS.fetch(request);
      // The monitor is a live page. Left to the default asset headers the edge
      // cached it and kept serving the previous deploy's HTML to anyone who did
      // not bust the URL, so a redeploy silently reached nobody.
      if ((asset.headers.get("content-type") || "").includes("text/html")) {
        const fresh = new Response(asset.body, asset);
        fresh.headers.set("cache-control", "no-store, must-revalidate");
        fresh.headers.delete("etag");
        return fresh;
      }
      return asset;
    }
    return new Response("Not found", { status: 404 });
  },
};
