---
title: "Architecture"
updated: 2026-08-01
status: stable
---

`src/quantlab` owns deterministic data, portfolio, strategy, validation,
memory, autonomous scheduling and the read-only monitor. `tests` owns regression
coverage. A launchd service operates from an isolated runtime copy and exposes
only port 8766 on loopback. Cloudflare Tunnel publishes that read-only surface.
MeshKore carries public coordination but has no execution path into the host.
GitHub pull requests are the sole code-ingress path, protected by CI and human
review. Runtime data and credentials never enter Git.
