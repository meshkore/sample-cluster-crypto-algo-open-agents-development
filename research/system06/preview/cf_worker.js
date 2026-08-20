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
      await Promise.all(writes);
      return json(JSON.stringify({ ok: true, wrote: Object.keys(body) }));
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
      return json(JSON.stringify(s));
    }
    if (path === "/api/knowledge") {
      return json((await env.KV.get("knowledge")) || "{}");
    }
    if (path === "/api/detail") {
      const id = url.searchParams.get("id") || "";
      const dv = await env.KV.get("details");
      const map = dv ? JSON.parse(dv) : {};
      const d = map[id];
      if (!d) return json(JSON.stringify({ error: "not found" }), 404);
      return json(JSON.stringify(d));
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
