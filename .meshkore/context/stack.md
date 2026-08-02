---
title: "Stack"
updated: 2026-08-02
status: stable
---

| Layer | Locked choice |
|---|---|
| Runtime | Python 3.9+, standard-library core |
| Memory | SQLite; generated runtime DB is private |
| Market data | Public Binance Spot/USDT; local caches ignored |
| UI | Dependency-free HTML/CSS/JS served by Python |
| Supervisor | macOS launchd |
| Public edge | Cloudflare Worker + R2, push-only, permanent `workers.dev` |
| Collaboration | MeshKore WebSocket + GitHub fork/PR |
| CI | GitHub Actions, Python quality gates |
