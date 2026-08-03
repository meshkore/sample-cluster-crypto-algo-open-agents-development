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

console.log(`\n${passed} passed`);
