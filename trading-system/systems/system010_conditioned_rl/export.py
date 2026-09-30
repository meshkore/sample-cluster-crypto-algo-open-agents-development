"""Write an engine package the live layer can swap in. Task S10-12 fills this in.

`live-trading/` was built so that a better brain replaces the old one without resetting the
book: the trader re-reads `engines/current.json` between bars, rebuilds the brain, logs an
`ENGINE_SWAP` row, and carries on with the positions exactly as they stand. System 10 has to
fit that contract rather than extend it.

    live-trading/engines/v4-rl-<name>/
        manifest.json     provenance, the exams, the sealed reading, the levers it declares
        policy/           the exported policy
        region.json       the predicate, printable as rules
        features.json     the frozen feature registry and its content hash

The manifest's declared levers matter for a reason that has already bitten: the trader
refuses to trade degraded. If an overlay a lever depends on is missing or stale, `Channels`
would make that module abstain silently - a different strategy under the same name. So an
engine declares what it needs and the trader checks it can actually feed it before the first
bar.

Two rules on top, and neither is technical:

* The package is written only after S10-11 - the sealed reading - and only with that reading
  recorded in the manifest. An engine whose provenance says "promising" is how a laboratory
  talks itself into trading something it never measured.
* `current.json` is changed only on the operator's word, never by a script. Before that the
  package runs in a SHADOW paper book beside 06, on the same bars, published as a second
  curve.
"""

from __future__ import annotations

_TODO = "S10-12 implements the exporter, after the sealed reading of S10-11."


def write_engine_package(name: str, policy_dir: str, region_path: str, manifest: dict):
    """Write live-trading/engines/v4-rl-<name>/. Requires the sealed reading in `manifest`."""
    raise NotImplementedError(_TODO)
