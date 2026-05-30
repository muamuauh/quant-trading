"""Patch the vendored TradingAgents for two upstream incompatibilities.

TradingAgents/ is a vendored clone (gitignored), so these patches are not
committed with the repo and must be re-applied after a fresh
`git clone TradingAgents`. Run once after cloning:

    python scripts/patch_tradingagents.py

Idempotent: re-running detects each patch is already present and skips it.

----------------------------------------------------------------------------
Patch 1 — stockstats 'Date' column (dataflows/stockstats_utils.py)
  Newer yfinance names the date column "index" (not "Date") after reset_index,
  so _clean_dataframe does `data["Date"]` -> KeyError: 'Date', silently
  disabling the LLM technical analyst (~1900 errors/run).
  Fix: normalize the date column name.

Patch 2 — Reddit 403 (dataflows/reddit.py)
  Reddit blocks unauthenticated www.reddit.com/*.json with HTTP 403 since its
  2023 API change, spamming the log with warnings every run.
  Fix: add app-only OAuth (REDDIT_CLIENT_ID/SECRET) + degrade quietly (debug
  log, not warning) when no credentials.
----------------------------------------------------------------------------
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


TA_ROOT = Path(__file__).resolve().parent.parent / "TradingAgents" / "tradingagents"
MARKER = "[qtf patch]"


@dataclass
class Patch:
    name: str
    target: Path
    old: str
    new: str


PATCHES = [
    Patch(
        name="stockstats-date-column",
        target=TA_ROOT / "dataflows" / "stockstats_utils.py",
        old='''def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse dates, drop invalid rows, fill price gaps."""
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])''',
        new='''def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse dates, drop invalid rows, fill price gaps."""
    # Newer yfinance versions name the date column "index" / "Datetime" (or leave
    # it blank) after reset_index, instead of "Date". Normalize it so stockstats
    # finds "Date" -- without this every indicator lookup raises KeyError: 'Date'.
    # [qtf patch] see scripts/patch_tradingagents.py
    if "Date" not in data.columns:
        for alt in ("Datetime", "index", "date", "Unnamed: 0"):
            if alt in data.columns:
                data = data.rename(columns={alt: "Date"})
                break
        else:
            if len(data.columns) > 0:
                data = data.rename(columns={data.columns[0]: "Date"})
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])''',
    ),
    Patch(
        name="reddit-oauth-quiet",
        target=TA_ROOT / "dataflows" / "reddit.py",
        old='''import json
import logging
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_API = "https://www.reddit.com/r/{sub}/search.json?{qs}"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

# Default subreddits ordered roughly by signal density for ticker-specific
# discussion. wallstreetbets has the most volume but most noise; stocks /
# investing trend more measured. Caller can override.
DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")


def _fetch_subreddit(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict]:
    qs = urlencode({
        "q": ticker,
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",  # last 7 days
        "limit": limit,
    })
    url = _API.format(sub=sub, qs=qs)
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Reddit fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return []
    children = (payload.get("data") or {}).get("children") or []
    return [c.get("data", {}) for c in children if isinstance(c, dict)]''',
        new='''import base64
import json
import logging
import os
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# [qtf patch] Reddit blocks unauthenticated www.reddit.com/*.json with HTTP 403
# since its 2023 API change. Set REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET
# (register a free "script" app at https://www.reddit.com/prefs/apps) for OAuth.
# Without credentials we fall back to the public endpoint (403) but log at debug
# level so it doesn't spam the run log -- sentiment still has News + StockTwits.
_API = "https://www.reddit.com/r/{sub}/search.json?{qs}"
_OAUTH_API = "https://oauth.reddit.com/r/{sub}/search?{qs}"
_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

# Default subreddits ordered roughly by signal density for ticker-specific
# discussion. wallstreetbets has the most volume but most noise; stocks /
# investing trend more measured. Caller can override.
DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")

_TOKEN_CACHE: dict = {"token": None, "exp": 0.0}


def _get_oauth_token(timeout: float):
    """App-only (client_credentials) Reddit OAuth token, cached until expiry.
    Returns None when no credentials are configured."""
    cid = os.getenv("REDDIT_CLIENT_ID")
    secret = os.getenv("REDDIT_CLIENT_SECRET")
    if not cid or not secret:
        return None
    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["exp"] > now + 60:
        return _TOKEN_CACHE["token"]
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    data = urlencode({"grant_type": "client_credentials"}).encode()
    req = Request(_TOKEN_URL, data=data, headers={
        "Authorization": f"Basic {auth}", "User-Agent": _UA,
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
        token = payload.get("access_token")
        _TOKEN_CACHE["token"] = token
        _TOKEN_CACHE["exp"] = now + float(payload.get("expires_in", 3600))
        return token
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, ValueError) as exc:
        logger.debug("Reddit OAuth token fetch failed: %s", exc)
        return None


def _fetch_subreddit(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict]:
    qs = urlencode({
        "q": ticker,
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",  # last 7 days
        "limit": limit,
    })
    token = _get_oauth_token(timeout)
    if token:
        url = _OAUTH_API.format(sub=sub, qs=qs)
        headers = {"User-Agent": _UA, "Authorization": f"bearer {token}"}
    else:
        url = _API.format(sub=sub, qs=qs)
        headers = {"User-Agent": _UA, "Accept": "application/json"}
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        # 403 on the public endpoint without OAuth is expected -- debug, not
        # warning, so it doesn't spam logs. Set REDDIT_CLIENT_ID/SECRET for access.
        logger.debug("Reddit fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return []
    children = (payload.get("data") or {}).get("children") or []
    return [c.get("data", {}) for c in children if isinstance(c, dict)]''',
    ),
]


def main() -> int:
    if not TA_ROOT.exists():
        print(f"[skip] TradingAgents not found at {TA_ROOT.parent}")
        print("       Clone it first: git clone https://github.com/TauricResearch/TradingAgents")
        return 0

    rc = 0
    for p in PATCHES:
        if not p.target.exists():
            print(f"[warn] {p.name}: target missing {p.target}")
            rc = 1
            continue
        text = p.target.read_text(encoding="utf-8")
        if MARKER in text and p.old not in text:
            print(f"[ok] {p.name}: already patched")
            continue
        if p.old not in text:
            print(f"[warn] {p.name}: expected code not found (TradingAgents changed?) — patch manually")
            rc = 1
            continue
        p.target.write_text(text.replace(p.old, p.new), encoding="utf-8")
        print(f"[patched] {p.name}: {p.target.name}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
