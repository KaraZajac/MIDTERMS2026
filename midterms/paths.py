"""Repo-relative paths shared across midterms modules.

MIDTERMS_SOURCES overrides the raw-download directory (tests point it at a
fixture tree so they never touch real downloads).
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = Path(os.environ.get("MIDTERMS_SOURCES", ROOT / "sources"))
DATA = ROOT / "data"
CURATED = ROOT / "curated"          # hand-maintained facts (never generated)
RACES = DATA / "races"              # one table per chamber
POLLS = DATA / "polls"              # normalized poll records
HISTORY = DATA / "history"          # historical results for calibration
FORECAST = DATA / "forecast"        # model output: latest + dated snapshots
SITE = DATA / "site"                # JSON export for the Astro site

# Election constants
ELECTION_DAY = "2026-11-03"
HOUSE_SEATS = 435
HOUSE_MAJORITY = 218
