from __future__ import annotations

import sys
from pathlib import Path


# Make the plugin importable by its AstrBot package name when pytest is run
# directly from the cloned repository root.
PACKAGE_PARENT = Path(__file__).resolve().parents[2]
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))
