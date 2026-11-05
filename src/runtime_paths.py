"""Resource paths shared by source and packaged desktop installations."""

import os
from pathlib import Path


def font_directory() -> Path:
    configured = os.environ.get("JPARSE_FONT_DIR")
    return Path(configured) if configured else Path.home() / ".cache/babeldoc/fonts"
