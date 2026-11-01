"""Wikipedia pages via the MediaWiki action API, pinned by revision id.

Wikipedia's editors maintain the most complete openly licensed (CC BY-SA
4.0) compilation of 2026 race polling, expert ratings and candidate lists.
Pages move fast in the last week of a campaign, so every fetch records the
page's revision id in sources/manifest.yaml and data/meta.yaml; anyone can
reproduce a build exactly with ?oldid=<revid>.
"""

from __future__ import annotations

import json
import re
import time

from midterms.paths import SOURCES
from midterms.pipeline import fetch
from midterms.pipeline.htmltable import Table, wikitables

API = "https://en.wikipedia.org/w/api.php"
WIKI_DIR = SOURCES / "wikipedia"
_last_call = [0.0]


def slug(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")


def _polite() -> None:
    # Serial requests, ~1/s: well inside Wikimedia's API etiquette.
    wait = 1.0 - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def fetch_page(title: str, *, force: bool = False, max_age_hours: float | None = 6,
               oldid: int | None = None) -> dict:
    """Return {'title', 'revid', 'html'} for a page (cached under sources/)."""
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    dest = WIKI_DIR / f"{slug(title)}.json"
    if not force and oldid is None and fetch._fresh(dest, max_age_hours):
        return json.loads(dest.read_text())
    params = {"action": "parse", "prop": "text|revid", "formatversion": "2",
              "format": "json", "redirects": "1", "disableeditsection": "1",
              "disabletoc": "1", "maxlag": "5"}
    if oldid:
        params["oldid"] = str(oldid)
    else:
        params["page"] = title
    for attempt in range(4):
        _polite()
        payload = fetch.get_json(API, params=params)
        err = payload.get("error") if isinstance(payload, dict) else None
        if err and err.get("code") == "maxlag" and attempt < 3:
            time.sleep(5 * (attempt + 1))      # replicas lagging: back off
            continue
        break
    if "error" in payload:
        raise SystemExit(f"wikipedia: {title!r}: {payload['error'].get('info')}")
    p = payload["parse"]
    page = {"title": p["title"], "revid": p["revid"], "html": p["text"],
            "requested": title}
    dest.write_text(json.dumps(page))
    fetch.record(f"wikipedia:{title}", f"https://en.wikipedia.org/w/index.php?oldid={p['revid']}",
                 dest, revid=p["revid"], resolved_title=p["title"])
    print(f"  wiki {p['title']!r} rev {p['revid']} -> {fetch.shown(dest)}")
    return page


def tables(title: str, **kw) -> tuple[list[Table], dict]:
    page = fetch_page(title, **kw)
    return wikitables(page["html"]), page
