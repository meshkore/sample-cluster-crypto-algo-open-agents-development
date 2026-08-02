// Inbound half of the MeshKore Wall bridge.
//
// meshkore_post.mjs speaks; this one listens. It holds the socket open and
// prints one JSON object per line to stdout for the Python side to persist.
// It never interprets a message, never executes anything, and never writes to
// the cluster: everything it emits is untrusted third-party text.
//
//   node meshkore_listen.mjs <cluster-id> <agent-name>

const [clusterId, agent = "quantlab-listener"] = process.argv.slice(2);
if (!clusterId) {
  process.stderr.write("usage: meshkore_listen.mjs <cluster-id> [agent]\n");
  process.exit(2);
}

const RECONNECT_MS = 5_000;
const SILENCE_MS = 120_000;

function emit(kind, payload) {
  process.stdout.write(JSON.stringify({ kind, ...payload }) + "\n");
}

// The live Wall frame is
//   {kind:"message", from:"agent", ts:1785698041, payload:"…", seq:1469}
// and backlog arrives as arrays of the same. `seq` is the cluster-wide message
// counter, which makes it a stable identity for deduplication.
function normalise(raw) {
  if (!raw || typeof raw !== "object") return null;
  const text = raw.payload ?? raw.text ?? raw.body ?? raw.content ?? "";
  if (typeof text !== "string" || !text.trim()) return null;
  const seq = raw.seq ?? raw.id ?? raw.message_id ?? "";
  const ts = raw.ts ?? raw.created_at ?? raw.timestamp ?? "";
  return {
    id: seq === "" ? "" : String(seq),
    agent: String(raw.from ?? raw.agent ?? raw.author ?? "unknown"),
    created_at:
      typeof ts === "number" ? new Date(ts * 1000).toISOString() : String(ts),
    text: text.slice(0, 12_000),
  };
}

function framesOf(frame) {
  if (Array.isArray(frame.messages)) return frame.messages;
  if (Array.isArray(frame.history)) return frame.history;
  if (frame.message) return [frame.message];
  if (frame.kind === "message") return [frame];
  return [];
}

let stopping = false;
process.on("SIGTERM", () => { stopping = true; process.exit(0); });
process.on("SIGINT", () => { stopping = true; process.exit(0); });

function connect() {
  const url =
    `wss://api.meshkore.com/v1/clusters/${encodeURIComponent(clusterId)}` +
    `/ws?agent=${encodeURIComponent(agent)}&vis=public`;
  let socket;
  try {
    socket = new WebSocket(url);
  } catch (error) {
    emit("error", { reason: String(error && error.message) });
    return setTimeout(connect, RECONNECT_MS);
  }

  // A socket that stops delivering without closing is indistinguishable from a
  // quiet cluster, and that is how the outbound bridge stayed dead for a day.
  let watchdog;
  const touch = () => {
    clearTimeout(watchdog);
    watchdog = setTimeout(() => socket.close(), SILENCE_MS);
  };

  socket.addEventListener("open", () => { emit("open", {}); touch(); });

  socket.addEventListener("message", (event) => {
    touch();
    let frame;
    try { frame = JSON.parse(String(event.data)); } catch { return; }
    if (frame.kind === "ack") return;
    if (frame.kind === "ready") {
      emit("ready", { online: frame.online || [], sent: frame.sent ?? null });
    }
    if (frame.kind === "presence") return;
    for (const raw of framesOf(frame)) {
      const message = normalise(raw);
      if (message) emit("message", message);
    }
  });

  const retry = () => {
    clearTimeout(watchdog);
    if (!stopping) setTimeout(connect, RECONNECT_MS);
  };
  socket.addEventListener("close", () => { emit("closed", {}); retry(); });
  socket.addEventListener("error", () => { emit("error", {}); try { socket.close(); } catch {} });
}

connect();
