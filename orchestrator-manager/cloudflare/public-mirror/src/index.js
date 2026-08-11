const INDEX_KEY = "runners/index.json";
const SESSIONS_KEY = "sessions/index.json";
const MAX_BODY_BYTES = 5 * 1024 * 1024;
const MAX_TRACKED_RUNNERS = 40;
// Completed evaluations, not machines. Two labs can mint dozens of strategies
// a day; the sidebar must grow with those finishes, not stay stuck at "one row
// per hostname".
const MAX_TRACKED_SESSIONS = 120;
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

function sanitizeSessionId(value) {
  const slug = String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return slug || "session";
}

const runnerKey = (id) => `runner/${id}.json`;
const sessionKey = (id) => `session/${id}.json`;

async function readJsonArray(env, key) {
  const object = await env.STATE_BUCKET.get(key);
  if (!object) return [];
  try {
    const parsed = JSON.parse(await object.text());
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function readIndex(env) {
  return readJsonArray(env, INDEX_KEY);
}

async function readSessions(env) {
  return readJsonArray(env, SESSIONS_KEY);
}

function shortHash(text) {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function asStrategyView(value) {
  if (!value || typeof value !== "object") return null;
  if (value.backtest || value.definition || value.label) return value;
  // `forward_2026` is published as a flat portfolio-run row. Wrap it so the
  // archive and the Active tab share one shape.
  if (value.strategy_number == null && value.run_id == null) return null;
  const number = value.strategy_number;
  return {
    strategy_number: number,
    label:
      value.label ||
      (number != null ? `S${String(number).padStart(5, "0")}` : null),
    phase: value.status || null,
    validated: true,
    backtest: value,
  };
}

function strategyFingerprint(strategy, evidenceHint) {
  const view = asStrategyView(strategy);
  if (!view) return null;
  const backtest = view.backtest || {};
  const number = view.strategy_number ?? backtest.strategy_number;
  const label =
    view.label ||
    (number != null ? `S${String(number).padStart(5, "0")}` : null);
  if (number == null && !label) return null;
  const status =
    backtest.status || view.phase || evidenceHint || "COMPLETE";
  const ret = backtest.return_pct;
  const equity = backtest.final_equity ?? backtest.current_equity;
  const trades = backtest.trades;
  const runId = backtest.run_id || view.source_run_id || "";
  return [number, label, status, ret, equity, trades, runId].join("|");
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
    kind: "live",
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

function sessionCard(sessionId, runnerId, runnerLabel, strategy, evidence, receivedAt, fingerprint) {
  const view = asStrategyView(strategy);
  const backtest = view?.backtest || {};
  const forward = evidence === "FORWARD_2026";
  return {
    id: sessionId,
    kind: "session",
    fingerprint,
    runner_id: runnerId,
    label: runnerLabel,
    strategy_label: view?.label || null,
    last_seen: receivedAt,
    phase: forward ? "FORWARD_2026" : backtest.status || view?.phase || "COMPLETE",
    message: null,
    evidence: forward ? "FORWARD_2026" : "HISTORICAL_PHASE_1",
    return_pct: forward ? null : backtest.return_pct ?? null,
    current_equity: forward
      ? null
      : backtest.final_equity ?? backtest.current_equity ?? null,
    max_drawdown: backtest.max_drawdown ?? null,
    forward_return_pct: forward ? backtest.return_pct ?? null : null,
    forward_equity: forward
      ? backtest.final_equity ?? backtest.current_equity ?? null
      : null,
    has_best: false,
  };
}

async function archiveEvaluation(
  env,
  history,
  known,
  runnerId,
  runnerLabel,
  strategy,
  evidence,
  state,
  receivedAt
) {
  const fingerprint = strategyFingerprint(strategy, evidence);
  if (!fingerprint || known.has(fingerprint)) return history;
  const sessionId = sanitizeSessionId(
    `${runnerId}-${shortHash(fingerprint)}-${evidence === "FORWARD_2026" ? "fwd" : "p1"}`
  );
  const card = sessionCard(
    sessionId,
    runnerId,
    runnerLabel,
    strategy,
    evidence,
    receivedAt,
    fingerprint
  );
  const view = asStrategyView(strategy);
  const frozen = {
    version: 1,
    fingerprint,
    archived_at: receivedAt,
    evidence,
    runner: { id: runnerId, label: runnerLabel },
    strategy: view,
    // Freeze the whole public snapshot so a past row can reopen the monitor
    // as it looked when that evaluation finished.
    state: {
      ...state,
      current_strategy: view,
      last_completed_strategy: view,
      mirror: {
        ...(state.mirror || {}),
        edge_received_at: receivedAt,
        viewing: "session",
        session_id: sessionId,
      },
    },
  };
  await env.STATE_BUCKET.put(sessionKey(sessionId), JSON.stringify(frozen), {
    httpMetadata: { contentType: "application/json" },
  });
  known.add(fingerprint);
  return [card, ...history.filter((item) => item.id !== sessionId)];
}

async function maybeArchiveSessions(env, runnerId, runnerLabel, state, receivedAt) {
  let history = await readSessions(env);
  const known = new Set(history.map((item) => item.fingerprint).filter(Boolean));
  history = await archiveEvaluation(
    env,
    history,
    known,
    runnerId,
    runnerLabel,
    state.last_completed_strategy,
    "HISTORICAL_PHASE_1",
    state,
    receivedAt
  );
  const forward = asStrategyView(state.forward_2026);
  if (forward && (forward.backtest?.status === "FORWARD_2026" || forward.phase === "FORWARD_2026")) {
    history = await archiveEvaluation(
      env,
      history,
      known,
      runnerId,
      runnerLabel,
      forward,
      "FORWARD_2026",
      state,
      receivedAt
    );
  }
  const next = history
    .sort((a, b) => Date.parse(b.last_seen) - Date.parse(a.last_seen))
    .slice(0, MAX_TRACKED_SESSIONS);
  await env.STATE_BUCKET.put(SESSIONS_KEY, JSON.stringify(next), {
    httpMetadata: { contentType: "application/json" },
  });
  return next;
}


const BACKTEST_INDEX = "backtests/index.json";
const safeId = (id) => (/^[A-Za-z0-9._-]{1,64}$/.test(id) ? id : null);

async function putBacktest(rawId, request, env) {
  if (!allowed(request, env)) return reply({ error: "unauthorized" }, 401);
  const id = safeId(rawId);
  if (!id) return reply({ error: "invalid_id" }, 400);
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return reply({ error: "payload_too_large" }, 413);
  let detail;
  try {
    detail = JSON.parse(text);
  } catch {
    return reply({ error: "invalid_json" }, 400);
  }
  if (!detail?.run?.backtest_id) return reply({ error: "invalid_payload" }, 400);

  await env.STATE_BUCKET.put(`backtests/${id}.json`, JSON.stringify(detail), {
    httpMetadata: { contentType: "application/json" },
  });

  // The index is what the sidebar reads. Rebuilt from the summaries the daemon
  // sends rather than by listing the bucket: a list call is slow and, more to
  // the point, would order runs by key instead of by when they happened.
  const existing = await env.STATE_BUCKET.get(BACKTEST_INDEX);
  let index = [];
  if (existing) {
    try {
      index = JSON.parse(await existing.text());
    } catch {
      index = [];
    }
  }
  index = index.filter((row) => row.backtest_id !== id);
  index.unshift(detail.run);
  index.sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  index = index.slice(0, 500);
  await env.STATE_BUCKET.put(BACKTEST_INDEX, JSON.stringify(index), {
    httpMetadata: { contentType: "application/json" },
  });
  return reply({ stored: id, indexed: index.length }, 200);
}

// The loop's heartbeat: one object, overwritten. The archive says what
// finished; this says whether anything is happening at all, which for a loop
// that spends thirteen minutes of every fourteen inside a fit is most of what
// a visitor wants to know.
const LOOP_KEY = "loop/activity.json";

async function putLoopActivity(request, env) {
  if (!allowed(request, env)) return reply({ error: "unauthorized" }, 401);
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return reply({ error: "payload_too_large" }, 413);
  let document;
  try {
    document = JSON.parse(text);
  } catch {
    return reply({ error: "invalid_json" }, 400);
  }
  if (!document || typeof document !== "object" || Array.isArray(document)) {
    return reply({ error: "invalid_payload" }, 400);
  }
  document.edge_received_at = new Date().toISOString();
  await env.STATE_BUCKET.put(LOOP_KEY, JSON.stringify(document), {
    httpMetadata: { contentType: "application/json" },
  });
  return reply({ ok: true, edge_received_at: document.edge_received_at });
}

async function loopActivity(env) {
  const object = await env.STATE_BUCKET.get(LOOP_KEY);
  if (!object) return reply({}, 200);
  return new Response(await object.text(), {
    status: 200,
    headers: { ...JSON_HEADERS, "access-control-allow-origin": "*" },
  });
}

// The journal: every event of one hypothesis, in order.
//
// The live page reads these to draw the loop walking its seven stages. On this
// machine it gets them over a WebSocket the daemon serves by tailing the file;
// here it polls, because this Worker RECEIVES pushed snapshots and never holds
// a socket open to the laboratory. Same events, same order, either way -- the
// page cannot tell which transport delivered them, which is the point.
const JOURNAL_INDEX = "journal/index.json";
const journalKey = (id) => `journal/${id}.json`;

// A journal id names an object, so it is an allow-list rather than an escape.
function safeHypothesis(raw) {
  const id = String(raw || "").trim();
  if (!id || id.length > 40) return null;
  return /^[A-Za-z0-9_-]+$/.test(id) ? id : null;
}

async function putJournal(rawId, request, env) {
  if (!allowed(request, env)) return reply({ error: "unauthorized" }, 401);
  const id = safeHypothesis(rawId);
  if (!id) return reply({ error: "invalid_id" }, 400);
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return reply({ error: "payload_too_large" }, 413);
  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    return reply({ error: "invalid_json" }, 400);
  }
  const events = Array.isArray(payload?.events) ? payload.events : null;
  if (!events) return reply({ error: "invalid_payload" }, 400);

  // Last write wins on the whole hypothesis. The daemon sends the file it has,
  // which is the file the loop appended to, so the edge cannot end up with a
  // different ORDER than the laboratory -- only, briefly, with fewer events.
  await env.STATE_BUCKET.put(journalKey(id), JSON.stringify({ id, events }), {
    httpMetadata: { contentType: "application/json" },
  });

  let index = [];
  const existing = await env.STATE_BUCKET.get(JOURNAL_INDEX);
  if (existing) {
    try {
      index = JSON.parse(await existing.text());
    } catch {
      index = [];
    }
  }
  index = index.filter((row) => row.id !== id);
  index.unshift({ id, events: events.length, updated_at: new Date().toISOString() });
  index.sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
  index = index.slice(0, 200);
  await env.STATE_BUCKET.put(JOURNAL_INDEX, JSON.stringify(index), {
    httpMetadata: { contentType: "application/json" },
  });
  return reply({ ok: true, id, events: events.length });
}

async function getJournal(rawId, env) {
  // No id means the hypothesis in flight, so the page needs nothing to start.
  let id = safeHypothesis(rawId);
  if (!id) {
    const beat = await env.STATE_BUCKET.get(LOOP_KEY);
    if (beat) {
      try {
        id = safeHypothesis(JSON.parse(await beat.text())?.hypothesis);
      } catch {
        id = null;
      }
    }
  }
  if (!id) return reply({ id: "", events: [] }, 200);
  const object = await env.STATE_BUCKET.get(journalKey(id));
  if (!object) return reply({ id, events: [] }, 200);
  return new Response(await object.text(), {
    status: 200,
    headers: { ...JSON_HEADERS, "access-control-allow-origin": "*" },
  });
}

async function journalIndex(env) {
  const object = await env.STATE_BUCKET.get(JOURNAL_INDEX);
  if (!object) return reply({ journals: [] }, 200);
  try {
    return reply({ journals: JSON.parse(await object.text()) }, 200);
  } catch {
    return reply({ journals: [] }, 200);
  }
}

// `era` for a row published before the daemon started sending one.
//
// Only a fallback, and deliberately a partial one: it recovers the field the
// champion card depends on, so a stale index cannot go on crowning a training
// run, but it does NOT invent `pair_key`. That one is a hash of the genome and
// guessing at it here would be a second, drifting implementation of exactly the
// thing this whole change exists to stop having two of. Rows without it simply
// show no twin until the daemon republishes them.
function withEra(row) {
  if (!row || row.era) return row;
  let from = "";
  try {
    from = String(JSON.parse(row.strategy_params_json || "{}").trade_from || "");
  } catch {
    from = "";
  }
  from = from || String(row.window_start || "");
  return { ...row, traded_from: from, era: from >= "2026-01-01" ? "2026" : "training" };
}

async function backtestIndex(env) {
  const object = await env.STATE_BUCKET.get(BACKTEST_INDEX);
  if (!object) return reply({ best_2026: null, live: [], history: [] }, 200);
  let rows = [];
  try {
    rows = JSON.parse(await object.text());
  } catch {
    rows = [];
  }
  const live = rows.filter((r) => r.status === "running").map(withEra);
  const done = rows.filter((r) => r.status !== "running").map(withEra);
  // Same rule as the local monitor: best in the sealed forward window, then
  // whatever is running, then history in the order it happened.
  // `trades > 0` mirrors the local store exactly. A configuration that stands
  // aside for all of 2026 posts +0.00%, which beats every honest loss, so the
  // public champion became a flat line on zero trades and outranked eighteen
  // real results. Abstaining is not a result.
  //
  // `era === "2026"` is the clause that was WRONG here. This asked only whether
  // a run ENDED after 2026-01-01, and every training run that stops at the
  // boundary satisfies that -- so the page's champion card carried
  // `blackmac-codex-vrsi-v3-validation` at +10.14%, earned entirely between
  // 2022 and 2025, under a heading that says "best result in 2026". The daemon
  // now derives `era` and sends it; this asks the answer instead of computing
  // its own.
  const forward = done.filter(
    (r) => r.return_pct != null && r.era === "2026" && Number(r.trades || 0) > 0,
  );
  // The tiebreak is not decoration. Two runs tied on return were ordered by
  // whatever each store happened to return, so the edge and the local monitor
  // named different champions for the same data.
  forward.sort(
    (a, b) =>
      (b.return_pct || 0) - (a.return_pct || 0) ||
      String(b.created_at || "").localeCompare(String(a.created_at || "")) ||
      String(a.backtest_id || "").localeCompare(String(b.backtest_id || "")),
  );
  return reply(
    { best_2026: forward[0] || null, live, history: done },
    200,
  );
}

async function backtestDetail(rawId, env) {
  const id = safeId(rawId);
  if (!id) return reply({ error: "invalid_id" }, 400);
  const object = await env.STATE_BUCKET.get(`backtests/${id}.json`);
  if (!object) return reply({ error: "not_found" }, 404);
  return new Response(await object.text(), {
    status: 200,
    headers: { "content-type": "application/json", "access-control-allow-origin": "*" },
  });
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
  await maybeArchiveSessions(env, runnerId, label, state, receivedAt);

  return reply({ ok: true, edge_received_at: receivedAt, runner_id: runnerId });
}

async function runs(env) {
  // `runners` = live machines (one row each, updated in place).
  // `sessions` = finished evaluations that accumulate across publishes.
  const runners = await readIndex(env);
  const sessions = await readSessions(env);
  return reply({ runners, sessions });
}

function pickDefaultRunner(index) {
  // Prefer a lab whose crowned 2026 result actually made money. Otherwise a
  // newer empty or losing lab blanks / downgrades the public champion page.
  const profitable = index
    .filter(
      (item) =>
        item.evidence === "FORWARD_2026" &&
        typeof item.forward_return_pct === "number" &&
        item.forward_return_pct > 0
    )
    .sort((a, b) => b.forward_return_pct - a.forward_return_pct);
  if (profitable[0]) return profitable[0].id;
  const newest = index[0];
  if (newest?.has_best || newest?.evidence === "FORWARD_2026") return newest.id;
  const crowned = index.find((item) => item.evidence === "FORWARD_2026");
  if (crowned) return crowned.id;
  const withBest = index.find((item) => item.has_best);
  if (withBest) return withBest.id;
  return newest?.id;
}

async function latest(env, requestedRunnerId, requestedSessionId) {
  if (requestedSessionId) {
    const sessionId = sanitizeSessionId(requestedSessionId);
    const object = await env.STATE_BUCKET.get(sessionKey(sessionId));
    if (!object) {
      return reply({ status: "unknown_session", session_id: sessionId }, 404);
    }
    let frozen;
    try {
      frozen = JSON.parse(await object.text());
    } catch {
      return reply({ status: "corrupt_session", session_id: sessionId }, 404);
    }
    const state = frozen.state || frozen;
    return reply(state);
  }
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
    // Backtests, stored one object per run so the deployed page can offer the
    // whole archive rather than only whatever fitted in the last snapshot.
    if (url.pathname === "/api/backtests" && request.method === "GET") {
      return backtestIndex(env);
    }
    if (url.pathname.startsWith("/api/backtests/") && request.method === "GET") {
      return backtestDetail(url.pathname.slice("/api/backtests/".length), env);
    }
    if (url.pathname.startsWith("/api/backtests/") && request.method === "POST") {
      return putBacktest(url.pathname.slice("/api/backtests/".length), request, env);
    }
    if (url.pathname === "/api/loop" && request.method === "POST") {
      return putLoopActivity(request, env);
    }
    if (url.pathname === "/api/loop" && request.method === "GET") {
      return loopActivity(env);
    }
    // The same capability question the daemon answers. `false` is the whole
    // point: nothing on the internet may open a connection back to the
    // laboratory, so the live page polls here and sockets there, and asking
    // beats discovering it through a failed handshake.
    if (url.pathname === "/health" && request.method === "GET") {
      return reply({ status: "ok", websocket: false }, 200);
    }
    if (url.pathname === "/api/journals" && request.method === "GET") {
      return journalIndex(env);
    }
    if (url.pathname === "/api/journal" && request.method === "GET") {
      return getJournal(null, env);
    }
    if (url.pathname.startsWith("/api/journal/") && request.method === "GET") {
      return getJournal(url.pathname.slice("/api/journal/".length), env);
    }
    if (url.pathname.startsWith("/api/journal/") && request.method === "POST") {
      return putJournal(url.pathname.slice("/api/journal/".length), request, env);
    }
    if (url.pathname === "/api/runs" && request.method === "GET") return runs(env);
    // `/api/dashboard` is the endpoint the local monitor's UI fetches. Serving
    // the same path here lets this Worker host that exact page unmodified, so
    // the public view can never drift from the one on the operator's machine.
    // `?runner=<id>` selects one live machine; `?session=<id>` reopens a
    // finished evaluation; omitted, it follows the best available lab.
    if ((url.pathname === "/api/state" || url.pathname === "/api/dashboard") && request.method === "GET") {
      return latest(
        env,
        url.searchParams.get("runner"),
        url.searchParams.get("session")
      );
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
