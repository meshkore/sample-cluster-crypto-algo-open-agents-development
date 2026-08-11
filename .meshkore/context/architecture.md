---
title: "Architecture"
updated: 2026-08-11
status: stable
---

Four top-level folders, and the dependency direction between the first three is
the whole point — see `CONTRACT.md`. `backtester/` is the frozen instrument and
decides nothing. `trading-system/` holds every decision and is what contributors
change. `orchestrator-manager/` is the lab that runs them: the research loop,
the ledger, the SQLite database, the daemon and the public mirror Worker.
`monitor/public/` is the page itself. `tests` under each package own regression
coverage. A launchd service operates from an isolated runtime copy under
`~/Library/Application Support/QuantLab` and exposes only port 8766 on loopback.

**Before changing the monitor, or launching a run you expect it to display
correctly, read [[docs/architecture/monitor-frontend]].** It is the data
contract: the two-era model (`training` vs the sealed `2026`), how `era` and
`pair_key` are derived rather than stored, which fields a run row must carry,
the loop heartbeat's shape, and the three copies of the page that must be kept
in step. The page guesses nothing — data arriving in a shape it cannot interpret
is where every defect on this surface has come from.

Every public surface is outbound-only, so nothing on the internet can open a
connection to the host. The daemon pushes a redacted, size-bounded snapshot to
a Cloudflare Worker, which stores it in R2 and serves the monitor at a
permanent `workers.dev` address; the page is the same file the daemon serves.
MeshKore carries public coordination over outbound WebSockets and has no
execution path into the host. Full detail in [[docs/ops/infrastructure]].

GitHub pull requests are the sole code-ingress path, protected by CI and human
review. Runtime data and credentials never enter Git.
