"""Convert per-instrument scores to target weights via equal-weight top-K."""

from __future__ import annotations

import pandas as pd

from qtf.data.schema import code_from_symbol


def topk_equal_weight(
    scores: pd.Series,
    k: int = 3,
    market: str = "US",
    total_weight: float = 0.90,
) -> dict[str, float]:
    """`scores` is indexed by instrument symbol (e.g. 'aapl').

    Returns {'US.AAPL': total_weight/k, ...}. total_weight=0.90 leaves 10% cash
    buffer so the min_cash risk gate (default 5%) passes by a margin.
    """
    if scores.empty:
        return {}
    k = min(k, len(scores))
    chosen = scores.head(k)  # already sorted desc by latest_date_scores
    w = total_weight / k
    return {code_from_symbol(sym, market=market): w for sym in chosen.index}
