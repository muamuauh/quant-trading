"""End-to-end daily run: ingest → predict → strategy → risk → execute.

By default, does NOT retrain (use 02_train.py for that). Pass `--retrain` to retrain.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from qtf.agents.review import review_candidates
from qtf.config import settings, load_universe
from qtf.data.ingest import ingest_all
from qtf.data.schema import code_from_symbol
from qtf.execution.moomoo_executor import MoomooExecutor
from qtf.execution.order_planner import plan_orders
from qtf.model.train import train
from qtf.report.daily_report import generate as generate_report
from qtf.risk.gates import run_all_gates
from qtf.strategy.predict import latest_date_scores, load_latest_predictions
from qtf.strategy.topk_weights import topk_equal_weight
from qtf.utils.logging import get_logger, log_event


log = get_logger(__name__)


def _wait_for_positions(
    executor: MoomooExecutor,
    expected_codes: set[str],
    max_wait_sec: float = 30.0,
    poll_interval_sec: float = 2.0,
) -> None:
    """Poll moomoo until all `expected_codes` appear in positions, or timeout.

    moomoo's paper account has a several-second eventual-consistency lag
    between order fill and position_list_query reflecting the new holding,
    even though `total_assets` / `cash` update immediately. Without this
    wait, the daily report's positions table can miss tickers and the
    per-position `today_pl_val` sum becomes inconsistent with the
    account-level cumulative P&L. Account-level totals stay accurate
    regardless, but the report looks confusing.
    """
    start = time.time()
    while time.time() - start < max_wait_sec:
        try:
            current = set(executor.current_qty().keys())
        except Exception as e:  # noqa: BLE001 — keep polling on transient failures
            log_event(log, "cycle.wait.error", error=str(e))
            current = set()
        if expected_codes.issubset(current):
            log_event(log, "cycle.wait.done",
                      waited_sec=round(time.time() - start, 1),
                      positions=sorted(current))
            return
        time.sleep(poll_interval_sec)
    log_event(log, "cycle.wait.timeout",
              max_wait_sec=max_wait_sec,
              missing=sorted(expected_codes - current))


def last_close_from_csv() -> dict[str, float]:
    """Read the last close per ticker from staged CSVs. Returns {moomoo_code: price}."""
    out: dict[str, float] = {}
    csv_dir: Path = settings.raw_csv_dir
    for path in csv_dir.glob("*.csv"):
        df = pd.read_csv(path)
        if df.empty:
            continue
        symbol = path.stem
        out[code_from_symbol(symbol)] = float(df.iloc[-1]["close"])
    return out


def run_daily(*, skip_ingest: bool = False, retrain: bool = False, dry_run: bool = False,
              write_report: bool = True) -> dict:
    if not skip_ingest:
        log_event(log, "cycle.ingest")
        ingest_all()
    if retrain:
        log_event(log, "cycle.train")
        train()

    log_event(log, "cycle.predict")
    pred = load_latest_predictions()
    scores = latest_date_scores(pred)
    log_event(log, "cycle.scores", top=scores.head(5).to_dict())

    weights = topk_equal_weight(scores, k=5)
    log_event(log, "cycle.weights", weights=weights)

    agent_verdicts: list[dict] = []
    if settings.qtf_agents_enabled:
        log_event(log, "cycle.agents.review")
        weights, verdicts = review_candidates(weights)
        agent_verdicts = [v.as_dict() for v in verdicts]
        log_event(log, "cycle.agents.filtered", kept_weights=weights)

    log_event(log, "cycle.executor.init")
    executor = MoomooExecutor()
    portfolio = executor.get_portfolio()
    funds = portfolio.get("funds", {})
    positions = portfolio.get("positions", [])
    total_equity = float(funds.get("total_assets", 0.0))
    current_cash = float(funds.get("cash", 0.0))
    current_qty = {p["code"]: float(p["qty"]) for p in positions}
    today_pnl = sum(float(p.get("today_pl_val", 0.0)) for p in positions)

    last_close = last_close_from_csv()
    orders = plan_orders(
        target_weights=weights,
        current_qty=current_qty,
        last_close=last_close,
        total_equity=total_equity,
    )
    log_event(log, "cycle.orders", orders=[o.as_dict() for o in orders])

    ok, gates = run_all_gates(
        target_weights=weights,
        orders=orders,
        current_cash=current_cash,
        total_equity=total_equity,
        today_pnl=today_pnl,
    )
    log_event(log, "cycle.risk", passed=ok, gates=[g.__dict__ for g in gates])
    if not ok:
        log_event(log, "cycle.aborted", reason="risk gates failed")
        cycle_result = {
            "submitted": False,
            "orders": [o.as_dict() for o in orders],
            "gates": [g.__dict__ for g in gates],
            "agent_verdicts": agent_verdicts,
        }
    else:
        results = executor.submit(orders, dry_run=dry_run)
        log_event(log, "cycle.done", results=results)
        cycle_result = {
            "submitted": not dry_run,
            "orders": [o.as_dict() for o in orders],
            "gates": [g.__dict__ for g in gates],
            "results": results,
            "agent_verdicts": agent_verdicts,
        }

        # Give moomoo's position_list_query a chance to catch up before the
        # report snapshot reads it. Otherwise the positions table can miss
        # just-filled orders even though total_assets already reflects them.
        if not dry_run:
            submitted_codes = {
                r["code"] for r in results
                if r.get("status") == "submitted" and r.get("code")
            }
            if submitted_codes:
                log_event(log, "cycle.wait.start", expected=sorted(submitted_codes))
                _wait_for_positions(executor, submitted_codes)

    if write_report:
        try:
            report_path, _ = generate_report(cycle_result=cycle_result)
            cycle_result["report_path"] = str(report_path) if report_path else None
        except Exception as e:  # noqa: BLE001 — never let a report failure kill the cycle
            log_event(log, "cycle.report.error", error=str(e))
            cycle_result["report_path"] = None

    return cycle_result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-ingest", action="store_true")
    p.add_argument("--retrain", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-report", action="store_true", help="Skip writing the daily report")
    args = p.parse_args()
    run_daily(skip_ingest=args.skip_ingest, retrain=args.retrain, dry_run=args.dry_run,
              write_report=not args.no_report)


if __name__ == "__main__":
    main()
