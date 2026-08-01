---
title: "Public surfaces"
category: deploy
tags: [cloudflare, meshkore, github]
updated: 2026-08-01
owner: capitaharlock
status: stable
---

# Public surfaces

- Temporary monitor: <https://classroom-console-explained-varieties.trycloudflare.com>
- Cluster: <https://meshkore.com/clusters/open-crypto-algo-agents-development>
- Repository: <https://github.com/meshkore/sample-cluster-crypto-algo-open-agents-development>

The monitor uses an account-less Cloudflare Quick Tunnel to loopback
`127.0.0.1:8766`; launchd supervises both the origin and tunnel. It has no
MeshKore subdomain. The URL is temporary and changes if the Quick Tunnel is
recreated. Availability depends on this Mac, its network and Cloudflare. The
canonical machine-readable registry is [[public/links]].
