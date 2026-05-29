"""Patch the vendored TradingAgents for a yfinance column-name incompatibility.

Problem: newer yfinance names the date column "index" (not "Date") after
reset_index, so TradingAgents' stockstats_utils._clean_dataframe does
`data["Date"]` -> KeyError: 'Date'. This silently disables the LLM technical
analyst (all indicator lookups fail, ~1900 errors per daily run) while the
rest of the agent review still runs.

Fix: normalize the date column name at the top of _clean_dataframe.

TradingAgents/ is a vendored clone (gitignored), so this patch is not committed
with the repo and must be re-applied after a fresh `git clone TradingAgents`.
Run this once after cloning:

    python scripts/patch_tradingagents.py

Idempotent: re-running detects the patch is already present and does nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path


TARGET = (
    Path(__file__).resolve().parent.parent
    / "TradingAgents" / "tradingagents" / "dataflows" / "stockstats_utils.py"
)

MARKER = "[qtf patch]"

OLD = '''def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse dates, drop invalid rows, fill price gaps."""
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])'''

NEW = '''def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
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
    data = data.dropna(subset=["Date"])'''


def main() -> int:
    if not TARGET.exists():
        print(f"[skip] TradingAgents not found at {TARGET}")
        print("       Clone it first: git clone https://github.com/TauricResearch/TradingAgents")
        return 0

    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"[ok] already patched: {TARGET}")
        return 0
    if OLD not in text:
        print(f"[warn] expected code block not found in {TARGET}")
        print("       TradingAgents may have changed; patch manually (see this file's docstring).")
        return 1

    TARGET.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print(f"[patched] {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
