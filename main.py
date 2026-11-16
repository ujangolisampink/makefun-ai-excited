"""Storm Dive — ai-excited-01 entry.

The entry image sits beside this file as entry.png (JPEG bytes under
that name, which the rules allow). This program copies it, unchanged,
to the output directory as entry.png.
"""

import os
import shutil
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / "entry.png"
DEST_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

DEST_DIR.mkdir(parents=True, exist_ok=True)
shutil.copyfile(SOURCE, DEST_DIR / "entry.png")
