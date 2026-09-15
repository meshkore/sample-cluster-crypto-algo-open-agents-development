"""`python -m mwmodel.archive.build` - adopt everything already on disk into the archive.

Downloads nothing. Every stream in the registry whose source file the catalogue already holds
is read, stamped with its publication lag, and written to the store; every stream whose source
has not been harvested is listed as missing, which is information rather than an error.
"""

from __future__ import annotations

import sys

from . import store
from .streams import registry


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    only = [a for a in argv if not a.startswith("-")] or None

    print("THE WORLD ARCHIVE - build")
    print(f"  registry {len(registry())} streams   store {store.WORLD_ROOT}")
    print("  adopting what the catalogue already holds; nothing is downloaded\n")

    manifest = store.build_all(only=only, quiet=False)
    ok = manifest["streams"]
    missing = manifest.get("missing", {})
    rows = sum(e["rows"] for e in ok.values())
    firsts = [e["first"] for e in ok.values() if e["first"]]

    print(f"\n  built    {len(ok)} streams, {rows:,} observations, "
          f"earliest {min(firsts) if firsts else '-'}")
    if missing:
        print(f"  missing  {len(missing)} streams whose source has not been harvested:")
        for sid, why in sorted(missing.items())[:12]:
            print(f"             {sid:<32s}{why[:70]}")
        if len(missing) > 12:
            print(f"             ... and {len(missing) - 12} more")
    print(f"  manifest {store.MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
