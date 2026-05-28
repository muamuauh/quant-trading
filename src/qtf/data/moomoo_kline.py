"""Thin wrapper around the moomoo skill's get_kline.py."""

from __future__ import annotations

import time

import pandas as pd

from qtf.data.schema import moomoo_to_qlib_df
from qtf.utils.subprocess_runner import run_skill


def fetch_daily_kline(
    code: str,
    start: str,
    end: str,
    rehab: str = "forward",
    timeout: int = 120,
) -> pd.DataFrame:
    """Fetch one ticker's daily K-line over [start, end] inclusive (YYYY-MM-DD).

    Returns a DataFrame with qlib columns: symbol, date, open, close, high, low, volume, factor.
    """
    payload = run_skill(
        "quote",
        "get_kline",
        code,
        "--ktype", "1d",
        "--start", start,
        "--end", end,
        "--rehab", rehab,
        timeout=timeout,
    )
    return moomoo_to_qlib_df(code, payload)


def fetch_universe(
    universe: list[str],
    start: str,
    end: str,
    rehab: str = "forward",
    sleep_between: float = 0.6,
) -> dict[str, pd.DataFrame]:
    """Fetch daily K-line for every ticker. Returns {code: df}."""
    out: dict[str, pd.DataFrame] = {}
    for code in universe:
        out[code] = fetch_daily_kline(code, start, end, rehab=rehab)
        time.sleep(sleep_between)  # respect the 60-req / 30-sec history rate limit
    return out
