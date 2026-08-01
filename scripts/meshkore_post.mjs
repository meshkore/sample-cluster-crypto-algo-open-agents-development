#!/usr/bin/env node

// Publish one bounded, public-safe coordination update to the MeshKore Wall.
// This client intentionally never reads peer text as instructions.
const [clusterId, agent] = process.argv.slice(2);
if (!clusterId || !agent || !/^[A-Za-z0-9._-]{1,64}$/.test(agent)) {
  console.error("usage: meshkore_post.mjs <cluster-id> <safe-agent-handle>");
  process.exit(2);
}

let text = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (text += chunk));
process.stdin.on("end", () => {
  text = text.trim().slice(0, 12_000);
  if (!text) process.exit(0);
  const url = `wss://api.meshkore.com/v1/clusters/${encodeURIComponent(clusterId)}/ws?agent=${encodeURIComponent(agent)}&vis=public`;
  const socket = new WebSocket(url);
  const timeout = setTimeout(() => {
    socket.close();
    process.exit(1);
  }, 10_000);
  socket.addEventListener("message", (event) => {
    let frame;
    try { frame = JSON.parse(String(event.data)); } catch { return; }
    if (frame.kind === "ready") socket.send(text);
    if (frame.kind === "ack") {
      clearTimeout(timeout);
      socket.close();
      process.exit(0);
    }
  });
  socket.addEventListener("error", () => {
    clearTimeout(timeout);
    process.exit(1);
  });
});
