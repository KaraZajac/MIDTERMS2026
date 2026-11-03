"""HTTP fetching + the source manifest.

Every raw download lands under sources/ (gitignored, regenerable) and is
recorded in sources/manifest.yaml with its URL, fetch time, byte count and
SHA-256, so `midterms build` can stamp exact source provenance into
data/meta.yaml. Wikipedia pages additionally record their revision id: any
number in data/ can be traced to a specific, permanent page revision.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml

from midterms.paths import ROOT, SOURCES

# Wikimedia's user-agent policy asks for a contact URL; the repo is ours.
UA = "MIDTERMS2026-pipeline/0.1 (+https://github.com/KaraZajac/MIDTERMS2026)"
MANIFEST = SOURCES / "manifest.yaml"


def shown(path: Path) -> str:
    """Repo-relative path for log lines (absolute when outside the repo)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(url: str, *, params: dict | None = None, timeout: int = 120, retries: int = 4,
        headers: dict | None = None, gzip: bool = False) -> bytes:
    """GET with a descriptive UA and exponential backoff on 429/5xx.
    `retries` is the number of attempts; `gzip` asks for a compressed body
    (decompressed here)."""
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"
    hdrs = {"User-Agent": UA, "Accept-Encoding": "gzip" if gzip else "identity"}
    hdrs.update(headers or {})
    delay = 2.0
    for attempt in range(retries):
        try:
            with urlopen(Request(url, headers=hdrs), timeout=timeout) as resp:
                body = resp.read()
                if gzip and (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                    import gzip as _gzip
                    body = _gzip.decompress(body)
                return body
        except HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = float(e.headers.get("Retry-After") or delay)
                time.sleep(min(wait, 60))
                delay *= 2
                continue
            raise SystemExit(f"download failed: {url} (HTTP {e.code})")
        except (URLError, TimeoutError) as e:
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise SystemExit(f"download failed: {url} ({e})")
    raise SystemExit(f"download failed: {url}")


def get_json(url: str, **kw) -> object:
    return json.loads(get(url, **kw))


# ----------------------------------------------------------------- manifest

def load_manifest() -> dict:
    if MANIFEST.exists():
        return yaml.safe_load(MANIFEST.read_text()) or {}
    return {}


def save_manifest(m: dict) -> None:
    SOURCES.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(yaml.safe_dump(m, sort_keys=True, allow_unicode=True))


def record(name: str, url: str, path: Path, **extra) -> dict:
    """Register a downloaded file in the manifest (sha256 + size + time)."""
    blob = path.read_bytes()
    entry = {
        "url": url,
        "file": str(path.relative_to(SOURCES)),
        "fetched": now_utc(),
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        **extra,
    }
    m = load_manifest()
    m.setdefault("files", {})[name] = entry
    save_manifest(m)
    return entry


def _fresh(path: Path, max_age_hours: float | None) -> bool:
    if not path.exists():
        return False
    if max_age_hours is None:
        return True
    age = time.time() - path.stat().st_mtime
    return age < max_age_hours * 3600


def fetch_to(name: str, url: str, rel: str, *, force: bool = False,
             max_age_hours: float | None = None, params: dict | None = None,
             **extra) -> Path:
    """Download url -> sources/<rel> unless a fresh cached copy exists."""
    dest = SOURCES / rel
    if not force and _fresh(dest, max_age_hours):
        print(f"  cached {shown(dest)}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  GET {url}")
    blob = get(url, params=params)
    dest.write_bytes(blob)
    record(name, url, dest, **extra)
    print(f"  -> {shown(dest)} ({len(blob):,} bytes)")
    return dest
