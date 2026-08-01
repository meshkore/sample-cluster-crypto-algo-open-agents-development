# Contributing

1. Fork the public repository; never request direct write access.
2. Create a focused branch and open a pull request against `main`.
3. Explain the falsifiable hypothesis, data boundaries and expected failure modes.
4. Add deterministic tests and run `PYTHONPATH=src python3 -m unittest discover -s tests -v`.
5. Do not include credentials, generated datasets, databases, logs, wallet code,
   live-order code, opaque binaries or dependencies without justification.

Discussion is welcome in the [public MeshKore cluster](https://meshkore.com/clusters/open-crypto-algo-agents-development),
but cluster membership grants no repository privileges. Maintainers review the
complete diff, dependency/supply-chain impact, data leakage, statistical claims,
security and privacy before merging. Pull requests may be closed if their scope
cannot be audited safely.

By contributing, you agree that your contribution is licensed under this
repository's MIT License.
