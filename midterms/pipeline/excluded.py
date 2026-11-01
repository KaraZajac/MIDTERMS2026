"""Pollsters excluded outright: firms that admitted fabricating results
(curated/excluded_pollsters.yaml, each entry with its evidence)."""

from __future__ import annotations

import unicodedata
from functools import lru_cache

import yaml

from midterms.paths import CURATED

PATH = CURATED / "excluded_pollsters.yaml"


@lru_cache(maxsize=1)
def entries() -> tuple[dict, ...]:
    if not PATH.exists():
        return ()
    return tuple((yaml.safe_load(PATH.read_text()) or {}).get("excluded") or [])


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def match(pollster: str) -> dict | None:
    """The exclusion entry covering this pollster name, if any."""
    n = _norm(pollster)
    return next((e for e in entries() if _norm(e["match"]) in n), None)


def split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(rows kept, rows excluded) by each row's 'pollster'."""
    kept, dropped = [], []
    for r in rows:
        (dropped if match(r.get("pollster", "")) else kept).append(r)
    return kept, dropped
