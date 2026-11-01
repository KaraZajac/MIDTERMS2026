"""`midterms pull` — fetch every source into sources/ (gitignored).

Groups (select with --only):

  wiki       Wikipedia: 35 Senate + 36 governor race pages, every state's
             House page, the generic-ballot polling template, the
             presidential-approval page, the three chamber overviews.
             CC BY-SA 4.0; each page pinned by revision id.
  votehub    VoteHub's public polls API — every poll in one JSON array.
             CC BY 4.0. Supplements Wikipedia's poll tables.
  pollsters  Silver Bulletin pollster ratings (Jan 2026; free use with
             attribution) and FiveThirtyEight's final (2024) ratings
             (CC BY 4.0) as the fallback for pollsters SB doesn't rate.
  fec        FEC bulk candidate summaries (public domain): 2026 for
             fundraising, 2018/2022 for the backtest.
  lean       2024/2020 presidential results by congressional district on
             the lines used in 2026.
  history    Past results for calibration (MEDSL; FEC official results).
  markets    Prediction-market prices (Kalshi, Polymarket), recorded as
             challengers for the scorecard — never model inputs.
"""

from __future__ import annotations

from midterms.pipeline import fetch, finance, lean, states, wiki

VOTEHUB = "https://api.votehub.com/polls"
SB_RATINGS = "https://www.natesilver.net/api/v1/file/9e28b3fd-62d8-4d41-bdd2-04d40a1b2eef.xlsx"
FTE_RATINGS = ("https://raw.githubusercontent.com/fivethirtyeight/data/master/"
               "pollster-ratings/pollster-ratings-combined.csv")


def pull_wiki(force: bool = False) -> None:
    titles = [t for _, _, t in states.race_pages()]
    titles += [states.GENERIC_BALLOT, states.APPROVAL, *states.OVERVIEW.values()]
    print(f"wikipedia: {len(titles)} pages")
    missing = []
    for t in titles:
        try:
            wiki.fetch_page(t, force=force, max_age_hours=None if not force else 0)
        except SystemExit as e:
            missing.append((t, str(e)))
    for t, e in missing:
        print(f"  ! {t}: {e}")


def pull_votehub(force: bool = False) -> None:
    print("votehub: polls API")
    fetch.fetch_to("votehub-polls", VOTEHUB, "votehub/polls.json", force=force,
                   max_age_hours=None if not force else 0)


def pull_pollsters(force: bool = False) -> None:
    print("pollster ratings")
    fetch.fetch_to("silver-bulletin-ratings", SB_RATINGS, "pollsters/silver-bulletin-2026-01.xlsx",
                   force=force)
    fetch.fetch_to("fte-pollster-ratings", FTE_RATINGS, "pollsters/fte-pollster-ratings-2024.csv",
                   force=force)


GROUPS = {
    "wiki": pull_wiki,
    "pollsters": pull_pollsters,
    "fec": finance.pull,
    "lean": lean.pull,
    "votehub": pull_votehub,
}


def main(only: list[str] | None = None, force: bool = False) -> None:
    for name, fn in GROUPS.items():
        if only and name not in only:
            continue
        fn(force=force)
    m = fetch.load_manifest()
    m["pulled"] = fetch.now_utc()
    fetch.save_manifest(m)
    print("✓ pull complete — next: midterms build")
