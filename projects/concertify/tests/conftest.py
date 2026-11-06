import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
for _sub in (BASE_DIR, BASE_DIR / "external", BASE_DIR / "services"):
    if str(_sub) not in sys.path:
        sys.path.insert(0, str(_sub))
