"""Run the opt-in Windows diagnostic from the source checkout."""

import multiprocessing
import sys
from pathlib import Path

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from dekstopshot.diagnostics import main

    raise SystemExit(main())
