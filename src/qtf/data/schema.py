"""Convert moomoo K-line JSON to qlib's expected CSV rows.

moomoo get_kline.py output shape:
    {"code": "US.AAPL", "ktype": "1d", "source": "history",
     "data": [{"time": "2024-01-02 00:00:00", "open": 187.15, "high": 188.44,
               "low": 183.89, "close": 185.64, "volume": 82488700, "turnover": ...}, ...]}

qlib CSV columns (per dump_bin convention, one file per symbol):
    symbol,date,open,close,high,low,volume,factor
    (the symbol column is what dump_bin uses to bucket; we set factor=1.0
     because moomoo returns forward-adjusted prices already.)
"""

from __future__ import annotations

import pandas as pd


QLIB_COLUMNS = ["symbol", "date", "open", "close", "high", "low", "volume", "factor"]


def moomoo_to_qlib_df(moomoo_code: str, kline_payload: dict) -> pd.DataFrame:
    """Build a qlib-compatible DataFrame for one ticker from one get_kline payload."""
    symbol = symbol_from_code(moomoo_code)
    bars = kline_payload.get("data", [])
    if not bars:
        return pd.DataFrame(columns=QLIB_COLUMNS)

    df = pd.DataFrame(bars)
    df["symbol"] = symbol
    df["date"] = pd.to_datetime(df["time"]).dt.strftime("%Y-%m-%d")
    df["factor"] = 1.0
    df = df[QLIB_COLUMNS]
    df = df.drop_duplicates(subset=["symbol", "date"]).sort_values("date").reset_index(drop=True)
    return df


def symbol_from_code(moomoo_code: str) -> str:
    """`US.AAPL` -> `aapl` (qlib convention is lowercase)."""
    if "." in moomoo_code:
        return moomoo_code.split(".", 1)[1].lower()
    return moomoo_code.lower()


def code_from_symbol(symbol: str, market: str = "US") -> str:
    """`aapl` -> `US.AAPL`."""
    return f"{market.upper()}.{symbol.upper()}"
