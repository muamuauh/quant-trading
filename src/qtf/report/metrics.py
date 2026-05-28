"""Pure-function PnL / drawdown / win-rate calculations from the equity history."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class EquityMetrics:
    inception_date: str | None
    days_recorded: int
    first_equity: float
    last_equity: float
    inception_pnl_abs: float
    inception_pnl_pct: float       # decimal, e.g. 0.0235 = +2.35%
    peak_equity: float
    peak_date: str | None
    current_drawdown_pct: float    # decimal, negative or 0
    max_drawdown_pct: float        # decimal, the worst drawdown over history
    max_drawdown_date: str | None
    positive_days: int
    negative_days: int
    win_rate: float                # positive_days / (positive + negative)
    best_day_pnl: float
    best_day_date: str | None
    worst_day_pnl: float
    worst_day_date: str | None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def compute_metrics(history: pd.DataFrame) -> EquityMetrics:
    """Compute lifetime equity metrics from the snapshot history."""
    if history.empty:
        return EquityMetrics(
            inception_date=None, days_recorded=0, first_equity=0.0, last_equity=0.0,
            inception_pnl_abs=0.0, inception_pnl_pct=0.0,
            peak_equity=0.0, peak_date=None,
            current_drawdown_pct=0.0, max_drawdown_pct=0.0, max_drawdown_date=None,
            positive_days=0, negative_days=0, win_rate=0.0,
            best_day_pnl=0.0, best_day_date=None,
            worst_day_pnl=0.0, worst_day_date=None,
        )

    df = history.sort_values("date").reset_index(drop=True)
    first_eq = float(df.iloc[0]["total_assets"])
    last_eq = float(df.iloc[-1]["total_assets"])

    running_peak = df["total_assets"].cummax()
    dd = (df["total_assets"] - running_peak) / running_peak.where(running_peak > 0, 1.0)
    peak_idx = df["total_assets"].idxmax()
    worst_dd_idx = dd.idxmin()

    pos_mask = df["today_pnl"] > 0
    neg_mask = df["today_pnl"] < 0
    pos_days = int(pos_mask.sum())
    neg_days = int(neg_mask.sum())
    win_rate = pos_days / (pos_days + neg_days) if (pos_days + neg_days) else 0.0

    best_idx = df["today_pnl"].idxmax()
    worst_idx = df["today_pnl"].idxmin()

    return EquityMetrics(
        inception_date=str(df.iloc[0]["date"]),
        days_recorded=len(df),
        first_equity=first_eq,
        last_equity=last_eq,
        inception_pnl_abs=last_eq - first_eq,
        inception_pnl_pct=(last_eq / first_eq - 1.0) if first_eq else 0.0,
        peak_equity=float(df.iloc[peak_idx]["total_assets"]),
        peak_date=str(df.iloc[peak_idx]["date"]),
        current_drawdown_pct=float(dd.iloc[-1]),
        max_drawdown_pct=float(dd.iloc[worst_dd_idx]),
        max_drawdown_date=str(df.iloc[worst_dd_idx]["date"]),
        positive_days=pos_days,
        negative_days=neg_days,
        win_rate=win_rate,
        best_day_pnl=float(df.iloc[best_idx]["today_pnl"]),
        best_day_date=str(df.iloc[best_idx]["date"]),
        worst_day_pnl=float(df.iloc[worst_idx]["today_pnl"]),
        worst_day_date=str(df.iloc[worst_idx]["date"]),
    )
