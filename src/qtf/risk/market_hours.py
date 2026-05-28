"""US regular trading hours check via pandas_market_calendars."""

from __future__ import annotations

from datetime import datetime, timezone


def is_us_rth_now(now: datetime | None = None) -> bool:
    """True if `now` is within today's NYSE regular session."""
    import pandas_market_calendars as mcal
    import pandas as pd

    nyse = mcal.get_calendar("NYSE")
    now_utc = now or datetime.now(timezone.utc)
    today = now_utc.date()
    sched = nyse.schedule(start_date=str(today), end_date=str(today))
    if sched.empty:
        return False
    open_ts = sched.iloc[0]["market_open"].to_pydatetime()
    close_ts = sched.iloc[0]["market_close"].to_pydatetime()
    return open_ts <= pd.Timestamp(now_utc).to_pydatetime() <= close_ts
