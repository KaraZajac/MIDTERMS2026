"""State reference data and the Wikipedia page titles the pipeline reads."""

from __future__ import annotations

import yaml

from midterms.paths import CURATED

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}
ABBR = {v: k for k, v in STATES.items()}
AT_LARGE = {"AK", "DE", "ND", "SD", "VT", "WY"}


def chambers() -> dict:
    return yaml.safe_load((CURATED / "chambers.yaml").read_text())


# States whose House coverage Wikipedia splits across several pages
SPLIT_HOUSE = {"CA": ["(districts 1–26)", "(districts 27–52)"]}


def house_titles(st: str) -> list[str]:
    if st in AT_LARGE:
        return [f"2026 United States House of Representatives election in {STATES[st]}"]
    base = f"2026 United States House of Representatives elections in {STATES[st]}"
    if st in SPLIT_HOUSE:
        return [f"{base} {part}" for part in SPLIT_HOUSE[st]]
    return [base]


def senate_title(st: str, special: bool = False) -> str:
    kind = "special election" if special else "election"
    return f"2026 United States Senate {kind} in {STATES[st]}"


def governor_title(st: str) -> str:
    return f"2026 {STATES[st]} gubernatorial election"


def race_pages() -> list[tuple[str, str, str]]:
    """(race id, chamber, page title) for every statewide race, and
    (state, 'house', title) for each state's House page."""
    cur = chambers()
    out = []
    for st in cur["senate"]["class2"]:
        out.append((f"senate:{st}", "senate", senate_title(st)))
    for st in cur["senate"]["specials"]:
        out.append((f"senate:{st}-special", "senate", senate_title(st, special=True)))
    for st in cur["governor"]["up"]:
        out.append((f"governor:{st}", "governor", governor_title(st)))
    for st in STATES:
        for title in house_titles(st):
            out.append((f"house:{st}", "house", title))
    return out


GENERIC_BALLOT = "Template:2026 United States elections/polling"
APPROVAL = "Opinion polling on the second Trump presidency"
OVERVIEW = {
    "house": "2026 United States House of Representatives elections",
    "senate": "2026 United States Senate elections",
    "governor": "2026 United States gubernatorial elections",
}
