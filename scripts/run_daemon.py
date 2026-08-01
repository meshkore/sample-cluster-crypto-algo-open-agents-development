#!/usr/bin/python3
"""LaunchAgent entry point; avoids SIP stripping PYTHONPATH for /usr/bin/python3."""

from pathlib import Path
import sys

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "src"))

from quantlab.cli import main  # noqa: E402

raise SystemExit(main())
