#!/usr/bin/env python3
"""Generate the synthetic sample rushes: scripts/gen_samples.py [OUT_DIR] (default: samples/)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from videoflow.samples import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
