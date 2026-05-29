"""Vectorized top-K daily-rebalance backtest over the qlib prediction set.

Flow:
  predictions (date × instrument score)  +  close prices (qlib bin)
        │
        ▼
  每天按 score 取 top-K，等权持有到下一交易日
        │
        ▼
  组合日收益序列  →  metrics.compute_metrics

Baseline benchmark = equal-weight buy-and-hold of the full universe.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from qtf.backtest.metrics import (
    BacktestMetrics,
    compute_metrics,
    equity_curve,
    information_coefficient,
)
from qtf.config import settings
from qtf.utils.logging import get_logger, log_event


log = get_logger(__name__)


@dataclass
class BacktestResult:
    strategy: BacktestMetrics
    benchmark: BacktestMetrics
    ic: float
    rank_ic: float
    k: int
    cost_per_turnover: float
    strategy_curve: pd.Series
    benchmark_curve: pd.Series
    daily_returns: pd.Series


def _init_qlib() -> None:
    import yaml
    import qlib

    cfg = yaml.safe_load(settings.workflow_yaml.read_text(encoding="utf-8"))
    qlib.init(**cfg["qlib_init"])


def load_close_prices(instruments: list[str], start: str, end: str) -> pd.DataFrame:
    """Return a wide DataFrame: index=date, columns=instrument, values=close."""
    from qlib.data import D

    df = D.features(instruments, ["$close"], start_time=start, end_time=end)
    if df.empty:
        return pd.DataFrame()
    close = df["$close"].unstack(level="instrument")  # date × instrument
    return close.sort_index()


def forward_returns_from_close(close: pd.DataFrame) -> pd.DataFrame:
    """Next-day simple return per instrument: r[t] = close[t+1]/close[t] - 1.

    Aligned so that a position decided using data up to day t earns r[t].
    """
    return close.shift(-1) / close - 1.0


def simulate_topk(
    predictions: pd.Series,
    fwd_returns_wide: pd.DataFrame,
    k: int = 5,
    cost_per_turnover: float = 0.0005,
) -> pd.Series:
    """Daily top-K equal-weight portfolio returns, net of turnover cost.

    `predictions`: MultiIndex (datetime, instrument) score.
    `fwd_returns_wide`: date × instrument next-day returns.
    Returns a date-indexed Series of net portfolio returns.
    """
    daily_ret: dict[pd.Timestamp, float] = {}
    prev_holdings: set[str] = set()

    dates = predictions.index.get_level_values("datetime").unique().sort_values()
    for dt in dates:
        if dt not in fwd_returns_wide.index:
            continue
        day_scores = predictions.xs(dt, level="datetime").sort_values(ascending=False)
        top = list(day_scores.head(k).index)
        if not top:
            continue

        fwd = fwd_returns_wide.loc[dt]
        rets = [fwd[s] for s in top if s in fwd.index and pd.notna(fwd[s])]
        if not rets:
            continue
        gross = sum(rets) / len(rets)  # equal weight

        # Turnover cost: fraction of book that changed names this rebalance.
        holdings = set(top)
        turnover = len(holdings.symmetric_difference(prev_holdings)) / (2 * k)
        cost = turnover * cost_per_turnover
        prev_holdings = holdings

        daily_ret[dt] = gross - cost

    return pd.Series(daily_ret).sort_index()


def equal_weight_benchmark(fwd_returns_wide: pd.DataFrame, dates: pd.Index) -> pd.Series:
    """Equal-weight buy-and-hold of the whole universe, restricted to `dates`."""
    bench = fwd_returns_wide.mean(axis=1)  # avg across all instruments per day
    return bench.reindex(dates).dropna()


def run_backtest(
    k: int = 5,
    cost_per_turnover: float = 0.0005,
    experiment_name: str = "us5_lgb",
) -> BacktestResult:
    """End-to-end: load predictions + prices, simulate, compute metrics."""
    from qtf.strategy.predict import load_latest_predictions

    _init_qlib()
    predictions = load_latest_predictions(experiment_name=experiment_name)

    dates = predictions.index.get_level_values("datetime")
    instruments = sorted(predictions.index.get_level_values("instrument").unique())
    start = str(dates.min().date())
    end = str(dates.max().date())
    log_event(log, "backtest.start", k=k, start=start, end=end,
              n_instruments=len(instruments))

    close = load_close_prices(instruments, start, end)
    fwd = forward_returns_from_close(close)

    strat_ret = simulate_topk(predictions, fwd, k=k, cost_per_turnover=cost_per_turnover)
    bench_ret = equal_weight_benchmark(fwd, strat_ret.index)

    # Forward returns as a MultiIndex series aligned to predictions for IC.
    fwd_long = fwd.stack()
    fwd_long.index = fwd_long.index.set_names(["datetime", "instrument"])
    ic, rank_ic = information_coefficient(predictions, fwd_long)

    strat_m = compute_metrics(strat_ret, bench_ret)
    bench_m = compute_metrics(bench_ret)

    log_event(log, "backtest.done",
              total_return=round(strat_m.total_return, 4),
              annual_return=round(strat_m.annual_return, 4),
              sharpe=round(strat_m.sharpe, 3),
              max_drawdown=round(strat_m.max_drawdown, 4),
              ic=round(ic, 4), rank_ic=round(rank_ic, 4))

    return BacktestResult(
        strategy=strat_m,
        benchmark=bench_m,
        ic=ic,
        rank_ic=rank_ic,
        k=k,
        cost_per_turnover=cost_per_turnover,
        strategy_curve=equity_curve(strat_ret),
        benchmark_curve=equity_curve(bench_ret),
        daily_returns=strat_ret,
    )
