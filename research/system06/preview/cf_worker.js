// system06-lab — public real-time laboratory dashboard.
// Serves the dashboard HTML + read-only JSON API from KV; a local pusher (on the
// machine running the autoloop) POSTs fresh state to /api/push with a bearer secret.
// The loop itself never runs here — this Worker only mirrors what the pusher sends.

const PUSH_STALE_MS = 30000; // if the local pusher stops sending, show the loop as not-live

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // ---- push endpoint (server-to-server, authenticated) ----
    if (path === "/api/push") {
      if (request.method !== "POST") return txt("method not allowed", 405);
      const auth = request.headers.get("authorization") || "";
      if (!env.PUSH_SECRET || auth !== "Bearer " + env.PUSH_SECRET) return txt("unauthorized", 401);
      let body;
      try { body = await request.json(); } catch { return txt("bad json", 400); }
      const writes = [];
      if (body.state !== undefined) writes.push(env.KV.put("state", JSON.stringify(body.state)));
      if (body.knowledge !== undefined) writes.push(env.KV.put("knowledge", JSON.stringify(body.knowledge)));
      if (body.details !== undefined) writes.push(env.KV.put("details", JSON.stringify(body.details)));
      if (body.page !== undefined) writes.push(env.KV.put("page", body.page));
      if (body.iterations !== undefined) writes.push(env.KV.put("iterations", JSON.stringify(body.iterations)));
      if (body.page_iterations !== undefined) writes.push(env.KV.put("page_iterations", body.page_iterations));
      if (body.systems !== undefined) writes.push(env.KV.put("systems", JSON.stringify(body.systems)));
      await Promise.all(writes);
      return json(JSON.stringify({ ok: true, wrote: Object.keys(body) }));
    }

    // ---- the execution switch (real-money kill switch) ----
    // Read by the local mirror before every venue order; anything but a fresh "on" is off.
    // Flipping it needs the operator PIN (Worker secret CONTROL_PIN); 8 wrong PINs in an
    // hour lock the endpoint for the rest of that hour.
    if (path === "/api/control") {
      if (request.method === "GET") return json(JSON.stringify(await control(env)));
      if (request.method !== "POST") return txt("method not allowed", 405);
      const hour = Math.floor(Date.now() / 3600000);
      const failKey = "control_fail_" + hour;
      const fails = parseInt((await env.KV.get(failKey)) || "0", 10);
      if (fails >= 8) return json(JSON.stringify({ ok: false, error: "locked for this hour" }), 429);
      let body;
      try { body = await request.json(); } catch { return txt("bad json", 400); }
      if (!env.CONTROL_PIN || !same(String(body.pin || ""), env.CONTROL_PIN)) {
        await env.KV.put(failKey, String(fails + 1), { expirationTtl: 7200 });
        return json(JSON.stringify({ ok: false, error: "wrong PIN" }), 401);
      }
      if (body.action !== "on" && body.action !== "off") return txt("action must be on|off", 400);
      const doc = { trading: body.action, at: new Date().toISOString(), by: "panel" };
      await env.KV.put("control", JSON.stringify(doc));
      return json(JSON.stringify({ ok: true, ...doc }));
    }

    // ---- read-only public API ----
    if (path === "/api/state") {
      const v = await env.KV.get("state");
      if (!v) return json("{}");
      let s;
      try { s = JSON.parse(v); } catch { return json(v); }
      // If the local pusher stopped, tell the public page honestly instead of
      // freezing on the last frame as if the loop were still working.
      const st = Date.parse(s.server_time || 0);
      if (st && (Date.now() - st) > PUSH_STALE_MS && s.running && s.running.running) {
        s.running = { ...s.running, running: false, stale: true, pusher_stale: true };
      }
      s.control = await control(env);
      return json(JSON.stringify(s));
    }
    if (path === "/api/systems") {
      // One entry per TRADING SYSTEM, each carrying its documentation as markdown -
      // the reading list a new system starts from. Written by cf_pusher from every
      // trading-system/quantlab_*/docs/context.json.
      return json((await env.KV.get("systems")) || "[]");
    }
    if (path === "/api/knowledge") {
      return json((await env.KV.get("knowledge")) || "{}");
    }
    if (path === "/api/iterations") {
      // The FULL run log - the home page carries only the freshest ten cards, so the
      // complete record lives here, one flat table the /iterations page renders.
      return json((await env.KV.get("iterations")) || '{"rows":[],"count":0}');
    }
    if (path === "/api/detail") {
      const id = url.searchParams.get("id") || "";
      const dv = await env.KV.get("details");
      const map = dv ? JSON.parse(dv) : {};
      const d = map[id];
      if (!d) return json(JSON.stringify({ error: "not found" }), 404);
      return json(JSON.stringify(d));
    }

    // ---- the full-history page ----
    if (path === "/iterations" || path === "/iterations.html") {
      const html = await env.KV.get("page_iterations");
      if (!html) return txt("La página de iteraciones aún no se ha publicado.", 503);
      return new Response(html, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
    }

    // ---- the dashboard page ----
    if (path === "/" || path === "/index.html" || path === "/dashboard.html") {
      const html = await env.KV.get("page");
      if (!html) return txt("El laboratorio aún no ha publicado datos. Vuelve en un momento.", 503);
      return new Response(html, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
    }
    return txt("not found", 404);
  }
};

function json(body, status = 200) {
  return new Response(body, { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}
function txt(body, status = 200) {
  return new Response(body, { status, headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" } });
}

async function control(env) {
  const v = await env.KV.get("control");
  try { return v ? JSON.parse(v) : { trading: "off", at: null, by: "default" }; }
  catch { return { trading: "off", at: null, by: "unreadable" }; }
}
function same(a, b) {
  // length-independent comparison so a wrong PIN takes the same time as a right one
  let d = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) d |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return d === 0;
}
