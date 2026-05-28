"""Capture today's portfolio snapshot and append to the equity-history CSV.

Schema of equity_history.csv (one row per trading day, lifetime ledger):
    date          ISO date YYYY-MM-DD
    total_assets  net asset value (USD)
    cash          available cash
    market_val    long market value
    today_pnl     today's realized + unrealized P&L (from moomoo's today_pl_val)
    positions     JSON string of [{code, qty, average_cost, nominal_price,
                                   market_val, unrealized_pl, pl_ratio_avg_cost}]

Re-running on the same date overwrites that row (so intra-day re-runs don't bloat the file).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from qtf.config import settings
from qtf.execution.moomoo_executor import MoomooExecutor
from qtf.utils.logging import get_logger, log_event


log = get_logger(__name__)

HISTORY_COLUMNS = ["date", "total_assets", "cash", "market_val", "today_pnl", "positions"]


@dataclass
class Snapshot:
    date: str
    funds: dict
    positions: list[dict]
    today_pnl: float

    @property
    def total_assets(self) -> float:
        return float(self.funds.get("total_assets", 0.0))

    @property
    def cash(self) -> float:
        return float(self.funds.get("cash", 0.0))

    @property
    def market_val(self) -> float:
        return float(self.funds.get("market_val", 0.0))


def capture(executor: MoomooExecutor | None = None, when: date | None = None) -> Snapshot:
    """Query moomoo for current portfolio. Pure read, no side-effects on disk."""
    executor = executor or MoomooExecutor()
    portfolio = executor.get_portfolio()
    funds = portfolio.get("funds", {})
    positions = portfolio.get("positions", [])
    today_pnl = sum(float(p.get("today_pl_val", 0.0)) for p in positions)
    snap = Snapshot(
        date=(when or date.today()).isoformat(),
        funds=funds,
        positions=positions,
        today_pnl=today_pnl,
    )
    log_event(log, "report.snapshot.captured",
              date=snap.date, total_assets=snap.total_assets,
              cash=snap.cash, today_pnl=today_pnl,
              n_positions=len(positions))
    return snap


def append_history(snap: Snapshot, csv_path: Path | None = None) -> Path:
    """Upsert this snapshot into the lifetime history CSV. Returns the file path."""
    path = csv_path or settings.equity_history_csv
    path.parent.mkdir(parents=True, exist_ok=True)

    row = {
        "date": snap.date,
        "total_assets": snap.total_assets,
        "cash": snap.cash,
        "market_val": snap.market_val,
        "today_pnl": snap.today_pnl,
        "positions": json.dumps(snap.positions, ensure_ascii=False),
    }

    if path.exists():
        df = pd.read_csv(path)
        df = df[df["date"] != snap.date]  # drop today's prior row if rerunning
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row], columns=HISTORY_COLUMNS)

    df = df.sort_values("date").reset_index(drop=True)
    df.to_csv(path, index=False)
    log_event(log, "report.history.appended", path=str(path), rows=len(df))
    return path


def load_history(csv_path: Path | None = None) -> pd.DataFrame:
    """Read the lifetime history CSV. Returns empty DataFrame if not yet created."""
    path = csv_path or settings.equity_history_csv
    if not path.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    return pd.read_csv(path)
