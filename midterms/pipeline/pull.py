"""`midterms pull` — fetch every source into sources/ (gitignored).

Groups (select with --only):

  wiki       Wikipedia: 35 Senate + 36 governor race pages, every state's
             House page, the generic-ballot polling template, the
             presidential-approval page, the three chamber overviews.
             CC BY-SA 4.0; each page pinned by revision id.
  votehub    VoteHub's public polls API — every poll in one JSON array.
             CC BY 4.0. Supplements Wikipedia's poll tables with the
             polls they lack (de-duplicated; see votehub.py).
  pollsters  Silver Bulletin pollster ratings (Jan 2026; free use with
             attribution) and FiveThirtyEight's final (2024) ratings
             (CC BY 4.0) as the fallback for pollsters SB doesn't rate.
             The build uses the pinned copy in data/pollster_ratings/.
  fec        FEC bulk candidate summaries (public domain): 2026 for
             fundraising, 2018/2022 for the backtest. If the download
             fails, the build keeps the committed filings.
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
    try:
        fetch.fetch_to("votehub-polls", VOTEHUB, "votehub/polls.json", force=force,
                       max_age_hours=None if not force else 0)
    except SystemExit as e:
        # a supplement, not the ledger: an outage must not stop a refresh.
        # build keeps the VoteHub polls already in data/polls/races.csv.
        print(f"  ! {e} — keeping the VoteHub polls already in the data")


def pull_pollsters(force: bool = False) -> None:
    """The raw ratings files. Not part of the refresh: the build uses the
    committed copy (data/pollster_ratings/) unless both files are here, and
    Silver Bulletin's has needed a login since Nov 1, 2026."""
    print("pollster ratings")
    for name, url, rel in (("silver-bulletin-ratings", SB_RATINGS, "pollsters/silver-bulletin-2026-01.xlsx"),
                           ("fte-pollster-ratings", FTE_RATINGS, "pollsters/fte-pollster-ratings-2024.csv")):
        try:
            fetch.fetch_to(name, url, rel, force=force)
        except SystemExit as e:
            print(f"  ! {e} — the build keeps data/pollster_ratings/")


FTE_GENERIC = ("https://web.archive.org/web/20250305204633id_/"
               "https://projects.fivethirtyeight.com/polls/data/generic_ballot_polls_historical.csv")
HISTORY = {
    "fec-results-2018": ("https://www.fec.gov/documents/2706/federalelections2018.xlsx",
                         "history/federalelections2018.xlsx"),
    "fec-results-2020": ("https://www.fec.gov/documents/4228/federalelections2020.xlsx",
                         "history/federalelections2020.xlsx"),
    "fec-results-2022": ("https://www.fec.gov/documents/5676/federalelections2022.xlsx",
                         "history/federalelections2022.xlsx"),
    "downballot-pres20-2022-lines": (
        "https://docs.google.com/spreadsheets/d/1CKngqOp8fzU22JOlypoxNsxL6KSAH920Whc-rd7ebuM/"
        "export?format=csv&gid=1913458313", "history/downballot-pres20-2022-lines.csv"),
    "downballot-pres-2018-lines": (
        "https://docs.google.com/spreadsheets/d/1zLNAuRqPauss00HDz4XbTH2HqsCzMe0pR8QmD1K8jk8/"
        "export?format=csv&gid=0", "history/downballot-pres-2018-lines.csv"),
    "fec-weball22": ("https://www.fec.gov/files/bulk-downloads/2022/weball22.zip", "history/weball22.zip"),
    "fec-weball18": ("https://www.fec.gov/files/bulk-downloads/2018/weball18.zip", "history/weball18.zip"),
    # FiveThirtyEight's generic-ballot poll archive (CC BY 4.0), as of the
    # March 2025 shutdown, via the Internet Archive: backtest input only
    "fte-generic-ballot-historical": (FTE_GENERIC, "history/fte-generic-ballot-polls-historical.csv"),
}


def pull_history(force: bool = False) -> None:
    """Inputs of `midterms backtest` (the historical Wikipedia race pages
    are fetched by the statewide backtest itself, pinned by revision)."""
    print("history: backtest inputs")
    for name, (url, rel) in HISTORY.items():
        fetch.fetch_to(name, url, rel, force=force)


GROUPS = {
    "wiki": pull_wiki,
    "pollsters": pull_pollsters,
    "fec": finance.pull,
    "lean": lean.pull,
    "votehub": pull_votehub,
    "history": pull_history,
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
