const INDEX_KEY = "runners/index.json";
const MAX_BODY_BYTES = 5 * 1024 * 1024;
const MAX_TRACKED_RUNNERS = 40;
const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

const reply = (value, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: JSON_HEADERS });
const allowed = (request, env) =>
  Boolean(env.PUBLISH_TOKEN) &&
  request.headers.get("authorization") === `Bearer ${env.PUBLISH_TOKEN}`;

// Several machines share one bearer token by design here — this is one
// operator's own computers, not an open public write endpoint — but the
// runner id still needs sanitizing before it becomes part of an R2 key or a
// JSON field an untrusted-by-default frontend renders.
function sanitizeRunnerId(value) {
  const slug = String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  return slug || "runner";
}
const runnerKey = (id) => `runner/${id}.json`;

async function readIndex(env) {
  const object = await env.STATE_BUCKET.get(INDEX_KEY);
  if (!object) return [];
  try {
    const parsed = JSON.parse(await object.text());
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function summarize(runnerId, label, state, receivedAt) {
  // Sidebar wants a short card: who, when, and preferably the 2026 forward
  // result rather than whatever Phase-1 candle is mid-flight. Champion evidence
  // is the authoritative 2026 number when present; otherwise fall back to a
  // best_strategy backtest that already carries FORWARD_2026 status.
  const current = state.current_strategy || null;
  const best = state.best_strategy || null;
  const champion = best?.champion || null;
  const activity = state.activity || {};
  const phase1 = current?.backtest || best?.backtest || {};
  let forwardReturn = null;
  let forwardEquity = null;
  let evidence = null;
  if (champion?.evidence === "FORWARD_2026") {
    forwardReturn = champion.return_pct ?? null;
    evidence = "FORWARD_2026";
  }
  const bestBacktest = best?.backtest || {};
  if (
    bestBacktest.status === "FORWARD_2026" ||
    best?.phase === "FORWARD_2026"
  ) {
    forwardReturn = forwardReturn ?? bestBacktest.return_pct ?? null;
    forwardEquity =
      bestBacktest.current_equity ?? bestBacktest.final_equity ?? null;
    evidence = evidence || "FORWARD_2026";
  }
  return {
    id: runnerId,
    label: label || runnerId,
    last_seen: receivedAt,
    phase: activity.phase || null,
    message: activity.message || null,
    strategy_label: (current || best)?.label || null,
    current_equity: phase1.current_equity ?? null,
    return_pct: phase1.return_pct ?? null,
    max_drawdown: phase1.max_drawdown ?? null,
    forward_return_pct: forwardReturn,
    forward_equity: forwardEquity,
    evidence,
    // Lets /api/dashboard (no query) prefer a lab that still has a crowned
    // champion over a freshly publishing machine whose DB has none yet.
    has_best: Boolean(best),
  };
}

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
  const runnerId = sanitizeRunnerId(payload.runner?.id);
  const label = String(payload.runner?.label || runnerId).slice(0, 80);
  const receivedAt = new Date().toISOString();
  const state = {
    ...payload.state,
    runner: { id: runnerId, label },
    mirror: {
      edge_received_at: receivedAt,
      source_published_at: payload.published_at || null,
    },
  };
  await env.STATE_BUCKET.put(runnerKey(runnerId), JSON.stringify(state), {
    httpMetadata: { contentType: "application/json" },
  });

  const index = await readIndex(env);
  const entry = summarize(runnerId, label, state, receivedAt);
  const next = [entry, ...index.filter((item) => item.id !== runnerId)]
    .sort((a, b) => Date.parse(b.last_seen) - Date.parse(a.last_seen))
    .slice(0, MAX_TRACKED_RUNNERS);
  await env.STATE_BUCKET.put(INDEX_KEY, JSON.stringify(next), {
    httpMetadata: { contentType: "application/json" },
  });

  return reply({ ok: true, edge_received_at: receivedAt, runner_id: runnerId });
}

async function runs(env) {
  return reply({ runners: await readIndex(env) });
}

function pickDefaultRunner(index) {
  // Follow the most recently seen runner when it has a published best/champion.
  // Otherwise fall back to the newest runner that still holds one — a machine
  // with an empty local DB must not blank the public "best strategy" page just
  // because it published a download heartbeat more recently.
  const newest = index[0];
  if (newest?.has_best || newest?.evidence === "FORWARD_2026") return newest.id;
  const crowned = index.find((item) => item.evidence === "FORWARD_2026");
  if (crowned) return crowned.id;
  const withBest = index.find((item) => item.has_best);
  if (withBest) return withBest.id;
  return newest.id;
}

async function latest(env, requestedRunnerId) {
  const index = await readIndex(env);
  if (!index.length) {
    return reply({ status: "waiting_for_local_runner", mirror: { edge_received_at: null } });
  }
  const runnerId = requestedRunnerId
    ? sanitizeRunnerId(requestedRunnerId)
    : pickDefaultRunner(index);
  const object = await env.STATE_BUCKET.get(runnerKey(runnerId));
  if (!object) {
    return reply({ status: "unknown_runner", runner_id: runnerId }, 404);
  }
  return new Response(await object.text(), { headers: JSON_HEADERS });
}

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
    if (url.pathname === "/api/runs" && request.method === "GET") return runs(env);
    // `/api/dashboard` is the endpoint the local monitor's UI fetches. Serving
    // the same path here lets this Worker host that exact page unmodified, so
    // the public view can never drift from the one on the operator's machine.
    // `?runner=<id>` selects one published session; omitted, it follows
    // whichever session was most recently seen.
    if ((url.pathname === "/api/state" || url.pathname === "/api/dashboard") && request.method === "GET") {
      return latest(env, url.searchParams.get("runner"));
    }
    if (request.method === "GET") {
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
