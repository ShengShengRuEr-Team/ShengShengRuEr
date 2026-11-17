"""Repository-relative paths shared by the console and its worker."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = Path(
    os.getenv("M3_CONSOLE_BACKEND_DIR", str(ROOT.parents[1] / "backend"))
).resolve()
if not (BACKEND / "app/module3/worker.py").is_file():
    raise RuntimeError(
        "M3_CONSOLE_BACKEND_DIR must point to this repository's backend directory"
    )
