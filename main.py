"""Source and PyInstaller entry point; keep freeze_support before importing Qt."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        from dekstopshot.diagnostics import main as diagnostics_main

        raise SystemExit(diagnostics_main(sys.argv[2:]))
    from dekstopshot.app import main

    raise SystemExit(main())
