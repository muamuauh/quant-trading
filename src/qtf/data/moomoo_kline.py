"""Thin wrapper around the moomoo skill's get_kline.py."""

from __future__ import annotations

import time

import pandas as pd

from qtf.data.schema import moomoo_to_qlib_df
from qtf.utils.logging import get_logger, log_event
from qtf.utils.subprocess_runner import MoomooSkillError, run_skill


log = get_logger(__name__)


def fetch_daily_kline(
    code: str,
    start: str,
    end: str,
    rehab: str = "forward",
    timeout: int = 120,
    max_retries: int = 3,
    retry_backoff: float = 5.0,
) -> pd.DataFrame:
    """Fetch one ticker's daily K-line over [start, end] inclusive (YYYY-MM-DD).

    Returns a DataFrame with qlib columns: symbol, date, open, close, high, low, volume, factor.

    Retries on transient OpenD failures (connection drop / request cancel
    such as ``NN_ProtoRet_ByDisConnOrCancel``). During a 50-ticker pull that
    can run ~1 hour, a single network blip would otherwise abort the whole
    pipeline. Each retry waits ``retry_backoff * attempt`` seconds.
    """
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
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
        except MoomooSkillError as e:
            last_err = e
            if attempt < max_retries:
                wait = retry_backoff * attempt
                log_event(log, "kline.fetch.retry",
                          code=code, attempt=attempt, max_retries=max_retries,
                          wait_sec=wait, error=str(e))
                time.sleep(wait)
            else:
                log_event(log, "kline.fetch.failed",
                          code=code, attempts=max_retries, error=str(e))
    raise last_err  # type: ignore[misc]


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
