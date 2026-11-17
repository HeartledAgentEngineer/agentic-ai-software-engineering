"""Stellt sicher, dass pytest die Portfoliomodule (shared_core.*, App-Server) findet."""

import sys
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))
