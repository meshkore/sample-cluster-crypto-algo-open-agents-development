---
title: "Architecture"
updated: 2026-08-02
status: stable
---

`src/quantlab` owns deterministic data, portfolio, strategy, validation,
memory, autonomous scheduling and the read-only monitor. `tests` owns regression
coverage. A launchd service operates from an isolated runtime copy and exposes
only port 8766 on loopback.

Every public surface is outbound-only, so nothing on the internet can open a
connection to the host. The daemon pushes a redacted, size-bounded snapshot to
a Cloudflare Worker, which stores it in R2 and serves the monitor at a
permanent `workers.dev` address; the page is the same file the daemon serves.
MeshKore carries public coordination over outbound WebSockets and has no
execution path into the host. Full detail in [[docs/ops/infrastructure]].

GitHub pull requests are the sole code-ingress path, protected by CI and human
review. Runtime data and credentials never enter Git.
