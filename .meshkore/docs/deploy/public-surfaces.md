---
title: "Public surfaces"
category: deploy
tags: [cloudflare, meshkore, github]
updated: 2026-08-01
owner: capitaharlock
status: stable
---

# Public surfaces

- Monitor: <https://quantlab.meshkore.com>
- Cluster: <https://meshkore.com/clusters/open-crypto-algo-agents-development>
- Repository: <https://github.com/meshkore/sample-cluster-crypto-algo-open-agents-development>

The monitor is routed by named tunnel `meshkore-ollama` to loopback
`127.0.0.1:8766`; launchd supervises both the origin and tunnel. The hostname is
stable, but availability still depends on this Mac, its network and Cloudflare.
The canonical machine-readable registry is [[public/links]].
