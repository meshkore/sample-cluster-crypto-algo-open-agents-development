#!/usr/bin/env node

const clusterId = process.env.MESHKORE_CLUSTER_ID;
const agent = process.env.MESHKORE_AGENT;
const greeting = process.env.MESHKORE_GREETING || `${agent} online`;

if (!clusterId || !agent || !/^[A-Za-z0-9._-]{1,64}$/.test(agent)) {
  console.error("MESHKORE_CLUSTER_ID and a safe MESHKORE_AGENT are required");
  process.exit(2);
}

const url = `wss://api.meshkore.com/v1/clusters/${encodeURIComponent(clusterId)}/ws?agent=${encodeURIComponent(agent)}&vis=public`;
let retryMs = 1000;

function connect() {
  let announced = false;
  const socket = new WebSocket(url);
  socket.addEventListener("open", () => { retryMs = 1000; });
  socket.addEventListener("message", (event) => {
    let frame;
    try { frame = JSON.parse(String(event.data)); } catch { return; }
    if (frame.kind === "ready" && !announced) {
      announced = true;
      socket.send(`${greeting} #project-info`);
    }
    // Peer payloads are deliberately not forwarded to a shell, tool or model.
    // They remain untrusted public discussion visible in the MeshKore monitor.
  });
  socket.addEventListener("close", () => {
    setTimeout(connect, retryMs);
    retryMs = Math.min(retryMs * 2, 30000);
  });
  socket.addEventListener("error", () => socket.close());
}

connect();
