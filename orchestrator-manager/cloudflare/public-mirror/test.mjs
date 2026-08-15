#!/usr/bin/env node
// Exercises the Worker's fetch handler against an in-memory stand-in for the
// R2 binding, without needing wrangler or a deployed edge. Run with:
//   node cloudflare/public-mirror/test.mjs
// There is no JS test runner elsewhere in this repository, so this stays a
// plain script with its own tiny assertion helper rather than pulling in a
// framework for one file.
import assert from "node:assert/strict";
import worker from "./src/index.js";

function memoryBucket() {
  const store = new Map();
  return {
    store,
    async put(key, value) {
      store.set(key, value);
    },
    async get(key) {
      if (!store.has(key)) return null;
      const value = store.get(key);
      return { text: async () => value };
    },
  };
}

function env(token = "secret") {
  return {
    PUBLISH_TOKEN: token,
    STATE_BUCKET: memoryBucket(),
    ASSETS: { fetch: async () => new Response("not-a-page", { status: 404 }) },
  };
}

async function post(environment, body, token = "secret") {
  const request = new Request("https://mirror.example/api/state", {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const response = await worker.fetch(request, environment);
  return { status: response.status, body: await response.json() };
}

async function get(environment, path) {
  const response = await worker.fetch(new Request(`https://mirror.example${path}`), environment);
  return { status: response.status, body: await response.json() };
}

let passed = 0;
async function test(name, fn) {
  await fn();
  passed += 1;
  console.log(`ok - ${name}`);
}

const payload = (runnerId, phase) => ({
  version: 1,
  published_at: new Date().toISOString(),
  runner: { id: runnerId, label: `Machine ${runnerId}` },
  state: {
    activity: { phase, message: "testing" },
    current_strategy: { label: `S-${runnerId}`, backtest: { current_equity: 101000, return_pct: 0.01 } },
  },
});

await test("rejects a request without the bearer token", async () => {
  const e = env();
  const result = await post(e, payload("mac-1", "RUNNING"), "wrong-token");
  assert.equal(result.status, 401);
});

await test("accepts a valid push and stores it under a sanitized runner key", async () => {
  const e = env();
  const result = await post(e, payload("Mac 1!!", "RUNNING"));
  assert.equal(result.status, 200);
  assert.equal(result.body.runner_id, "mac-1");
  assert.ok(e.STATE_BUCKET.store.has("runner/mac-1.json"));
});

await test("two runners publish independently and both show up in /api/runs", async () => {
  const e = env();
  await post(e, payload("mac-1", "RUNNING"));
  await post(e, payload("mac-2", "RESTING"));
  const { body } = await get(e, "/api/runs");
  assert.equal(body.runners.length, 2);
  const ids = body.runners.map((r) => r.id).sort();
  assert.deepEqual(ids, ["mac-1", "mac-2"]);
});

await test("/api/dashboard with no runner follows the most recently seen one", async () => {
  const e = env();
  await post(e, payload("mac-1", "RUNNING"));
  await new Promise((resolve) => setTimeout(resolve, 5));
  await post(e, payload("mac-2", "RESTING"));
  const { body } = await get(e, "/api/dashboard");
  assert.equal(body.runner.id, "mac-2");
});

await test("/api/dashboard?runner=<id> returns that specific session", async () => {
  const e = env();
  await post(e, payload("mac-1", "RUNNING"));
  await post(e, payload("mac-2", "RESTING"));
  const { body } = await get(e, "/api/dashboard?runner=mac-1");
  assert.equal(body.runner.id, "mac-1");
});

await test("an unknown runner id is a 404, not an empty 200", async () => {
  const e = env();
  await post(e, payload("mac-1", "RUNNING"));
  const result = await get(e, "/api/dashboard?runner=does-not-exist");
  assert.equal(result.status, 404);
});

await test("no runner has ever published yet", async () => {
  const e = env();
  const { body } = await get(e, "/api/dashboard");
  assert.equal(body.status, "waiting_for_local_runner");
});

await test("re-publishing the same runner id updates it in place, not twice", async () => {
  const e = env();
  await post(e, payload("mac-1", "RUNNING"));
  await post(e, payload("mac-1", "RESTING"));
  const { body } = await get(e, "/api/runs");
  assert.equal(body.runners.length, 1);
  assert.equal(body.runners[0].phase, "RESTING");
});

await test("a malformed payload is rejected before touching storage", async () => {
  const e = env();
  const result = await post(e, { version: 1 });
  assert.equal(result.status, 400);
  assert.equal(e.STATE_BUCKET.store.size, 0);
});

await test("default dashboard prefers a crowned runner over a newer empty lab", async () => {
  const e = env();
  // Older runner still holds the FORWARD_2026 champion.
  await post(e, {
    version: 1,
    published_at: new Date().toISOString(),
    runner: { id: "lab-with-champion", label: "Champion lab" },
    state: {
      activity: { phase: "RESTING", message: "idle" },
      best_strategy: {
        label: "S00743",
        phase: "FORWARD_2026",
        backtest: {
          status: "FORWARD_2026",
          return_pct: 0.035,
          final_equity: 103500,
        },
        champion: { evidence: "FORWARD_2026", return_pct: 0.035 },
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 5));
  // Newer runner publishes activity but has no champion yet.
  await post(e, {
    version: 1,
    published_at: new Date().toISOString(),
    runner: { id: "fresh-empty-lab", label: "Fresh lab" },
    state: {
      activity: { phase: "DOWNLOADING_DATA", message: "downloading" },
      current_strategy: {
        label: "S00004",
        backtest: { return_pct: -0.06, current_equity: 94000 },
      },
    },
  });
  const { body } = await get(e, "/api/dashboard");
  assert.equal(body.runner.id, "lab-with-champion");
  assert.equal(body.best_strategy.label, "S00743");
});

await test("index summary prefers 2026 forward evidence over a mid-flight Phase-1 candle", async () => {
  const e = env();
  const body = {
    version: 1,
    published_at: new Date().toISOString(),
    runner: { id: "mac-fwd", label: "Forward box" },
    state: {
      activity: { phase: "BACKTESTING", message: "still running phase 1" },
      current_strategy: {
        label: "S-LIVE",
        backtest: { current_equity: 99000, return_pct: -0.01 },
      },
      best_strategy: {
        label: "S-BEST",
        phase: "FORWARD_2026",
        backtest: {
          status: "FORWARD_2026",
          current_equity: 103500,
          final_equity: 103500,
          return_pct: 0.035,
        },
        champion: {
          evidence: "FORWARD_2026",
          return_pct: 0.035,
        },
      },
    },
  };
  await post(e, body);
  const { body: runs } = await get(e, "/api/runs");
  assert.equal(runs.runners.length, 1);
  const row = runs.runners[0];
  assert.equal(row.label, "Forward box");
  assert.equal(row.evidence, "FORWARD_2026");
  assert.equal(row.forward_return_pct, 0.035);
  assert.equal(row.forward_equity, 103500);
  // Phase-1 mid-flight numbers stay available but are not the headline.
  assert.equal(row.return_pct, -0.01);
});

await test("finished evaluations accumulate in sessions, heartbeats do not duplicate them", async () => {
  const e = env();
  const first = {
    version: 1,
    published_at: new Date().toISOString(),
    runner: { id: "lab-a", label: "Lab A" },
    state: {
      activity: { phase: "RESTING", message: "done" },
      last_completed_strategy: {
        strategy_number: 6,
        label: "S00006",
        phase: "COMPLETE",
        backtest: {
          status: "COMPLETE",
          return_pct: 0.19,
          final_equity: 119000,
          trades: 778,
        },
      },
    },
  };
  await post(e, first);
  await post(e, first); // same fingerprint — must not grow
  const second = {
    ...first,
    published_at: new Date().toISOString(),
    state: {
      activity: { phase: "RESTING", message: "done" },
      last_completed_strategy: {
        strategy_number: 7,
        label: "S00007",
        phase: "COMPLETE",
        backtest: {
          status: "COMPLETE",
          return_pct: -0.02,
          final_equity: 98000,
          trades: 120,
        },
      },
      forward_2026: {
        strategy_number: 6,
        run_id: "FWD2-S00006-20260802",
        status: "FORWARD_2026",
        return_pct: -0.029,
        final_equity: 97000,
        trades: 74,
      },
    },
  };
  await post(e, second);
  const { body } = await get(e, "/api/runs");
  assert.equal(body.runners.length, 1);
  assert.equal(body.sessions.length, 3); // S00006 phase1, S00007 phase1, S00006 forward
  const labels = body.sessions.map((s) => s.strategy_label).sort();
  assert.deepEqual(labels, ["S00006", "S00006", "S00007"]);
  const sessionId = body.sessions.find((s) => s.strategy_label === "S00007").id;
  const viewed = await get(e, "/api/dashboard?session=" + encodeURIComponent(sessionId));
  assert.equal(viewed.status, 200);
  assert.equal(viewed.body.current_strategy.label, "S00007");
  assert.equal(viewed.body.mirror.viewing, "session");
});

await test("default dashboard prefers a profitable 2026 champion over a newer losing lab", async () => {
  const e = env();
  await post(e, {
    version: 1,
    published_at: new Date().toISOString(),
    runner: { id: "winner", label: "Winner" },
    state: {
      activity: { phase: "RESTING" },
      best_strategy: {
        label: "S00743",
        phase: "FORWARD_2026",
        backtest: { status: "FORWARD_2026", return_pct: 0.035, final_equity: 103500 },
        champion: { evidence: "FORWARD_2026", return_pct: 0.035 },
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 5));
  await post(e, {
    version: 1,
    published_at: new Date().toISOString(),
    runner: { id: "loser", label: "Loser" },
    state: {
      activity: { phase: "DOWNLOADING_DATA" },
      best_strategy: {
        label: "S00006",
        phase: "FORWARD_2026",
        backtest: { status: "FORWARD_2026", return_pct: -0.029, final_equity: 97000 },
        champion: { evidence: "FORWARD_2026", return_pct: -0.029 },
      },
    },
  });
  const { body } = await get(e, "/api/dashboard");
  assert.equal(body.runner.id, "winner");
  assert.equal(body.best_strategy.label, "S00743");
});



// --- backtest archive (QUANT27) -------------------------------------------- #
// The deployed page must offer the whole history, not just the last snapshot,
// so runs are stored one object per id with an index the sidebar reads.

async function putRun(environment, run, token = "secret") {
  const request = new Request(`https://mirror.example/api/backtests/${run.backtest_id}`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ run, equity: [], orders: [], trades: [], decisions: [] }),
  });
  const response = await worker.fetch(request, environment);
  return { status: response.status, body: await response.json() };
}

const run = (id, over = {}) => ({
  backtest_id: id,
  label: id,
  status: "complete",
  created_at: "2026-08-01T10:00:00",
  window_start: "2022-01-01",
  window_end: "2025-12-31",
  return_pct: 0.1,
  // A run that traded. The champion rule requires it, so the default here is a
  // run that qualifies and the abstention is stated explicitly where it matters.
  trades: 12,
  // Every real payload carries `era`, derived by the daemon from the date
  // trading was allowed to START. The fixture carries it too: the worker
  // deriving its own answer is the bug these tests exist to catch.
  era: "training",
  traded_from: "2022-01-01",
  ...over,
});

// A run in the sealed window. Spelled out as its own helper because "ends after
// 2026-01-01" is NOT what makes a run forward evidence, and a fixture that only
// moved `window_end` is how the edge came to crown a 2022-2025 result.
const forward = (id, over = {}) =>
  run(id, { era: "2026", traded_from: "2026-01-01", window_end: "2026-12-31", ...over });

await test("a published run is stored and appears in the index", async () => {
  const e = env();
  assert.equal((await putRun(e, run("aaa"))).status, 200);
  const { body } = await get(e, "/api/backtests");
  assert.equal(body.history.length, 1);
  assert.equal(body.history[0].backtest_id, "aaa");
  const detail = await get(e, "/api/backtests/aaa");
  assert.equal(detail.status, 200);
  assert.equal(detail.body.run.backtest_id, "aaa");
});

await test("publishing requires the token", async () => {
  const e = env();
  assert.equal((await putRun(e, run("aaa"), "wrong")).status, 401);
  assert.equal((await get(e, "/api/backtests")).body.history.length, 0);
});

await test("re-publishing a run replaces it rather than duplicating", async () => {
  const e = env();
  await putRun(e, run("aaa", { return_pct: 0.1 }));
  await putRun(e, run("aaa", { return_pct: 0.9 }));
  const { body } = await get(e, "/api/backtests");
  assert.equal(body.history.length, 1);
  assert.equal(body.history[0].return_pct, 0.9);
});

await test("history is chronological, newest first, not ranked by return", async () => {
  const e = env();
  await putRun(e, run("old", { created_at: "2026-01-01T00:00:00", return_pct: 9.0 }));
  await putRun(e, run("new", { created_at: "2026-08-01T00:00:00", return_pct: -0.5 }));
  const { body } = await get(e, "/api/backtests");
  assert.deepEqual(body.history.map((r) => r.backtest_id), ["new", "old"]);
});

await test("best_2026 needs forward evidence, not merely the best return", async () => {
  const e = env();
  // A huge pre-2026 result must NOT be crowned: it never saw the sealed window.
  await putRun(e, run("historical", { return_pct: 47.0, window_end: "2025-12-31" }));
  await putRun(e, forward("forward", { return_pct: 0.03 }));
  const { body } = await get(e, "/api/backtests");
  assert.equal(body.best_2026.backtest_id, "forward");
});

await test("running runs are separated from history", async () => {
  const e = env();
  await putRun(e, run("live", { status: "running", return_pct: null }));
  await putRun(e, run("done"));
  const { body } = await get(e, "/api/backtests");
  assert.deepEqual(body.live.map((r) => r.backtest_id), ["live"]);
  assert.deepEqual(body.history.map((r) => r.backtest_id), ["done"]);
});

await test("an unknown or malformed id is a 404 or 400, never a crash", async () => {
  const e = env();
  assert.equal((await get(e, "/api/backtests/nope")).status, 404);
  assert.equal((await get(e, "/api/backtests/..%2Fetc")).status, 400);
});

await test("a run that never traded cannot be crowned, however flat it finished", async () => {
  // Exactly the bug this rule exists for: a configuration gated out of the
  // whole forward window posts +0.00%, which outranks every honest loss.
  const e = env();
  await putRun(e, forward("abstained", { return_pct: 0, trades: 0 }));
  await putRun(e, forward("traded", { return_pct: -0.07, trades: 67 }));
  const { body } = await get(e, "/api/backtests");
  assert.equal(body.best_2026.backtest_id, "traded");
  // and it is still in the archive -- refused as champion, not hidden
  assert.ok(body.history.some((r) => r.backtest_id === "abstained"));
});

await test("the crown goes to the better SHAPE, not the bigger return", async () => {
  // The operator's objection, as a test. A curve that returns far more and
  // gives a quarter of it back from its peak leaves whoever bought at the top
  // down 24%; a smaller, steadier one leaves them whole. Ranked on return the
  // first wins, and that is how this laboratory got the champion it got.
  const e = env();
  await putRun(e, forward("spike", {
    return_pct: 3.5, trades: 200,
    quality: { score: 0.11, worst_entry_return: -0.24, maximum_drawdown: 0.24 },
  }));
  await putRun(e, forward("steady", {
    return_pct: 0.29, trades: 140,
    quality: { score: 0.41, worst_entry_return: -0.02, maximum_drawdown: 0.066 },
  }));
  const { body } = await get(e, "/api/backtests");
  assert.equal(body.best_2026.backtest_id, "steady");
});

await test("a row published before the score existed is not silently disqualified", async () => {
  // Five hundred archived rows predate `quality`. Treating a missing score as
  // zero would empty the board at the moment the score shipped and crown the
  // first new run whatever it did. An old champion has to be BEATEN.
  const e = env();
  await putRun(e, forward("legacy", { return_pct: 0.42, trades: 90 }));
  const { body } = await get(e, "/api/backtests");
  assert.equal(body.best_2026.backtest_id, "legacy");
});

await test("a graded run outranks an ungraded one only on its own merits", async () => {
  // Once ANY row carries a score the board sorts on it, and an ungraded row
  // sorts below every graded one. That is the deliberate cost of the fallback
  // above: it keeps an old champion visible until something is measured against
  // the new criteria, and then the measured result wins.
  const e = env();
  await putRun(e, forward("legacy", { return_pct: 0.42, trades: 90 }));
  await putRun(e, forward("graded", { return_pct: 0.05, trades: 90, quality: { score: 0.3 } }));
  const { body } = await get(e, "/api/backtests");
  assert.equal(body.best_2026.backtest_id, "graded");
  assert.equal(body.history.length, 2);
});

await test("a run ending AT the lock is training, not forward evidence", async () => {
  // The bug this file did not catch, verbatim from the archive:
  // `blackmac-codex-vrsi-v3-validation` traded 2022-01-01 to 2025-12-31 and so
  // has `window_end` exactly at the boundary. The old filter asked only whether
  // a run ended after 2026-01-01, so it was crowned "best result in 2026" on a
  // +10.14% earned entirely in the years it had been fitted on -- the one
  // number this laboratory's rules say must never be contaminated.
  const e = env();
  await putRun(e, run("validation", {
    return_pct: 0.1014, trades: 117,
    window_start: "2021-01-01", window_end: "2026-01-01", traded_from: "2022-01-01",
  }));
  await putRun(e, forward("real-forward", { return_pct: 0.02, trades: 9 }));
  const { body } = await get(e, "/api/backtests");
  assert.equal(body.best_2026.backtest_id, "real-forward");
});

await test("a row published before `era` existed is still classified, not crowned by default", async () => {
  // The index survives a deploy. Until the daemon republishes, rows carry no
  // `era`, and a fallback that gave up would restore the old bug for exactly
  // as long as the archive went unrefreshed.
  const e = env();
  const stale = run("stale", { return_pct: 9.9, window_end: "2026-01-01" });
  delete stale.era;
  delete stale.traded_from;
  stale.strategy_params_json = JSON.stringify({ trade_from: "2022-01-01" });
  await putRun(e, stale);
  await putRun(e, forward("real-forward", { return_pct: 0.02, trades: 9 }));
  const { body } = await get(e, "/api/backtests");
  assert.equal(body.best_2026.backtest_id, "real-forward");
  assert.equal(body.history.find((r) => r.backtest_id === "stale").era, "training");
});

await test("no traded forward run leaves the champion empty rather than crowning an abstention", async () => {
  const e = env();
  await putRun(e, forward("abstained", { return_pct: 0, trades: 0 }));
  assert.equal((await get(e, "/api/backtests")).body.best_2026, null);
});

// ---- the loop's heartbeat ------------------------------------------------ //

async function postLoop(environment, body, token = "secret") {
  const request = new Request("https://mirror.example/api/loop", {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const response = await worker.fetch(request, environment);
  return { status: response.status, body: await response.json() };
}

await test("the heartbeat is stored and served", async () => {
  const e = env();
  assert.equal((await postLoop(e, { iteration: 47, module: "BEAR" })).status, 200);
  const { body } = await get(e, "/api/loop");
  assert.equal(body.iteration, 47);
  assert.equal(body.module, "BEAR");
  assert.ok(body.edge_received_at, "the edge stamps arrival, so a stale beat is visible");
});

await test("the heartbeat is overwritten, never accumulated", async () => {
  const e = env();
  await postLoop(e, { iteration: 47 });
  await postLoop(e, { iteration: 48 });
  assert.equal((await get(e, "/api/loop")).body.iteration, 48);
});

await test("writing a heartbeat requires the token", async () => {
  const e = env();
  assert.equal((await postLoop(e, { iteration: 47 }, "wrong")).status, 401);
  assert.deepEqual((await get(e, "/api/loop")).body, {});
});

await test("no heartbeat yet is an empty object, not a 404", async () => {
  // The page renders "the loop is not running" from this. A 404 would put the
  // whole refresh into its error branch and blank the archive with it.
  const e = env();
  const { status, body } = await get(e, "/api/loop");
  assert.equal(status, 200);
  assert.deepEqual(body, {});
});

await test("a malformed heartbeat is rejected before touching storage", async () => {
  const e = env();
  assert.equal((await postLoop(e, ["not", "an", "object"])).status, 400);
  assert.deepEqual((await get(e, "/api/loop")).body, {});
});

// ---------------------------------------------------------------- journal --
//
// The live diagram reads these. On the operator's machine it gets the same
// events over a WebSocket the daemon feeds by tailing the file; here it polls.
// What must hold in both is that the ORDER is the laboratory's order and that a
// page arriving mid-hypothesis gets the whole thing, not the tail.

async function postJournal(environment, id, body, token = "secret") {
  const request = new Request(`https://mirror.example/api/journal/${id}`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const response = await worker.fetch(request, environment);
  return { status: response.status, body: await response.json() };
}

const ev = (stage, node, extra = {}) => ({ at: "2026-08-11T19:00:00Z", stage, node, ...extra });

await test("a journal is stored whole and served in the laboratory's order", async () => {
  const e = env();
  const events = [ev("begin", "frame"), ev("consulting", "consult"), ev("fit", "fit")];
  assert.equal((await postJournal(e, "H-L090", { events })).status, 200);
  const { status, body } = await get(e, "/api/journal/H-L090");
  assert.equal(status, 200);
  assert.deepEqual(body.events.map((x) => x.stage), ["begin", "consulting", "fit"]);
});

await test("the journal is replaced, never appended twice", async () => {
  // Last write wins on the whole file. Merging deltas at the edge is the one
  // arrangement that could give the public a DIFFERENT order than the ledger.
  const e = env();
  await postJournal(e, "H-L090", { events: [ev("begin", "frame")] });
  await postJournal(e, "H-L090", { events: [ev("begin", "frame"), ev("fit", "fit")] });
  assert.equal((await get(e, "/api/journal/H-L090")).body.events.length, 2);
});

await test("no id serves the hypothesis the heartbeat says is in flight", async () => {
  // The page must be able to start with nothing but a URL.
  const e = env();
  await postJournal(e, "H-L091", { events: [ev("begin", "frame")] });
  await postLoop(e, { iteration: 91, hypothesis: "H-L091" });
  const { body } = await get(e, "/api/journal");
  assert.equal(body.id, "H-L091");
  assert.equal(body.events.length, 1);
});

await test("an unknown or unopened hypothesis is empty, never a 404", async () => {
  // Same reason as the heartbeat: a 404 puts the page into its error branch and
  // blanks a diagram that could still have drawn the stages it does know.
  const e = env();
  const { status, body } = await get(e, "/api/journal/H-L999");
  assert.equal(status, 200);
  assert.deepEqual(body.events, []);
});

await test("a journal id cannot escape its folder", async () => {
  const e = env();
  assert.equal((await postJournal(e, "..%2F..%2Fbacktests%2Findex", { events: [ev("x", "y")] })).status, 400);
  assert.deepEqual((await get(e, "/api/journal/..%2F..%2Fsecrets")).body.events, []);
});

await test("writing a journal requires the token", async () => {
  const e = env();
  assert.equal((await postJournal(e, "H-L090", { events: [ev("begin", "frame")] }, "wrong")).status, 401);
  assert.deepEqual((await get(e, "/api/journal/H-L090")).body.events, []);
});

await test("a journal without an events array is rejected before storage", async () => {
  const e = env();
  assert.equal((await postJournal(e, "H-L090", { events: "nope" })).status, 400);
});

await test("the journal index lists hypotheses newest first", async () => {
  const e = env();
  await postJournal(e, "H-L090", { events: [ev("begin", "frame")] });
  await postJournal(e, "H-L091", { events: [ev("begin", "frame"), ev("fit", "fit")] });
  const { journals } = (await get(e, "/api/journals")).body;
  assert.equal(journals[0].id, "H-L091");
  assert.equal(journals[0].events, 2);
  assert.equal(journals.length, 2);
});

await test("re-publishing a hypothesis does not duplicate its index row", async () => {
  const e = env();
  await postJournal(e, "H-L090", { events: [ev("begin", "frame")] });
  await postJournal(e, "H-L090", { events: [ev("begin", "frame"), ev("fit", "fit")] });
  const { journals } = (await get(e, "/api/journals")).body;
  assert.equal(journals.length, 1);
  assert.equal(journals[0].events, 2);
});

console.log(`\n${passed} passed`);
