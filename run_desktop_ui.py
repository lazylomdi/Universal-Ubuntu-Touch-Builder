#!/usr/bin/env python3
"""Launch the AndroidBuilder PySide6 desktop interface."""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
runpy.run_path(str(ROOT / "desktop_ui" / "app.py"), run_name="__main__")
