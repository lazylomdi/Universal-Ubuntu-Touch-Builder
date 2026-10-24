#!/usr/bin/env python3
"""Backward-compatible entry point for the ROMForge command-line application.

The maintained CLI implementation lives in :mod:`romforge`. This wrapper
keeps older commands that invoke `python3 main.py` working without duplicating
the CLI implementation or retaining the unresolved merge-conflict content
that previously made this file syntactically invalid.
"""

from romforge import main


if __name__ == "__main__":
    raise SystemExit(main())
