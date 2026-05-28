"""moomoo codes (`US.AAPL`) ↔ yfinance/TradingAgents tickers (`AAPL`).

TradingAgents uses yfinance under the hood, which expects bare US tickers
(no exchange prefix). HK uses suffix `.HK` in yfinance (e.g. `0700.HK`),
A-share uses `.SS` / `.SZ`. This module centralises the conversion so we
don't sprinkle string surgery across the codebase.
"""

from __future__ import annotations


def moomoo_to_yf(moomoo_code: str) -> str:
    """`US.AAPL` -> `AAPL`, `HK.00700` -> `0700.HK`, `SH.601318` -> `601318.SS`."""
    if "." not in moomoo_code:
        return moomoo_code
    prefix, sym = moomoo_code.split(".", 1)
    prefix = prefix.upper()
    if prefix == "US":
        return sym.upper()
    if prefix == "HK":
        # moomoo HK codes are zero-padded 5 digits; yfinance expects 4 digits
        return f"{sym.lstrip('0').zfill(4)}.HK"
    if prefix == "SH":
        return f"{sym}.SS"
    if prefix == "SZ":
        return f"{sym}.SZ"
    return moomoo_code  # pass through unknown prefixes
