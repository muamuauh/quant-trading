"""Backtest the trained model's top-K strategy over the test period.

Loads the latest mlflow predictions + qlib close prices, simulates a daily
top-K equal-weight rebalance, and writes reports/backtest_<date>.md with
Sharpe / max drawdown / annualized return / IC vs an equal-weight benchmark.

Run AFTER 02_train.py. Re-run after any config/hyperparameter change to see
whether the strategy got better or worse.
"""

from __future__ import annotations

import argparse
import os
import sys

from qtf.backtest.engine import run_backtest
from qtf.backtest.report import generate


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--k", type=int, default=5, help="top-K stocks to hold (default 5)")
    p.add_argument("--cost", type=float, default=0.0005,
                   help="per-turnover transaction cost, decimal (default 0.0005 = 5bp)")
    p.add_argument("--no-write", action="store_true", help="print only, don't write file")
    args = p.parse_args()

    result = run_backtest(k=args.k, cost_per_turnover=args.cost)
    path, md = generate(result, write_to_disk=not args.no_write)
    if path:
        print(f"Backtest report written: {path}\n")
    print(md)

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)  # skip qlib/joblib teardown noise (see scripts/02_train.py)


if __name__ == "__main__":
    main()
