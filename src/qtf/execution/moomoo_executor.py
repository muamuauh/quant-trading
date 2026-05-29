"""Submit planned orders to moomoo via the skill's place_order.py.

Never calls SDK unlock_trade — that must be done manually in the OpenD GUI per skill rules.
Defaults to TrdEnv.SIMULATE; REAL requires both .env (FUTU_TRD_ENV=REAL, I_CONFIRM_REAL=1)
and the risk gate `env_guard` to pass.
"""

from __future__ import annotations

from typing import Any

from qtf.config import settings
from qtf.execution.order_planner import Order
from qtf.utils.logging import get_logger, log_event
from qtf.utils.subprocess_runner import MoomooSkillError, run_skill


log = get_logger(__name__)


class MoomooExecutor:
    def __init__(self, acc_id: int | None = None, trd_env: str | None = None) -> None:
        self.acc_id = acc_id or settings.futu_acc_id
        self.trd_env = trd_env or settings.futu_trd_env
        if not self.acc_id:
            raise RuntimeError("FUTU_ACC_ID not set in .env — run get_accounts.py and fill it in.")

    def get_portfolio(self) -> dict[str, Any]:
        """Returns {'funds': {...}, 'positions': [...]} from the skill."""
        return run_skill(
            "trade", "get_portfolio",
            "--acc-id", str(self.acc_id),
            "--trd-env", self.trd_env,
        )

    def current_qty(self) -> dict[str, float]:
        """Convenience: {code: qty} mapping from the portfolio call."""
        portfolio = self.get_portfolio()
        return {p["code"]: float(p["qty"]) for p in portfolio.get("positions", [])}

    def total_equity(self) -> float:
        portfolio = self.get_portfolio()
        return float(portfolio.get("funds", {}).get("total_assets", 0.0))

    def snapshot_prices(self, codes: list[str]) -> dict[str, float]:
        """Live last-price per code via the skill's snapshot (no subscription needed).

        Used to price limit orders off the *current* market instead of a stale
        daily close — otherwise a stock that gapped/ran intraday gets a limit
        below market and never fills (see the ORCL +10% day).
        """
        if not codes:
            return {}
        try:
            payload = run_skill("quote", "get_snapshot", *codes)
        except MoomooSkillError as e:
            log_event(log, "execute.snapshot.error", error=str(e), codes=codes)
            return {}
        out: dict[str, float] = {}
        for row in payload.get("data", []):
            code = row.get("code")
            px = float(row.get("last_price", 0) or 0)
            if code and px > 0:
                out[code] = px
        return out

    def cancel_open_orders(self) -> list[str]:
        """Cancel all non-terminal (open) orders on this account. Returns cancelled ids.

        Prevents stale unfilled limit orders (status SUBMITTED / WAITING_SUBMIT /
        SUBMITTING) from accumulating across daily runs, which would otherwise
        risk double-fills the next time the planner sees qty=0 and re-buys.
        """
        terminal = {"FILLED_ALL", "CANCELLED_ALL", "FAILED", "DELETED",
                    "CANCELLED_PART", "FILLED_PART"}
        try:
            payload = run_skill(
                "trade", "get_orders",
                "--acc-id", str(self.acc_id),
                "--trd-env", self.trd_env,
            )
        except MoomooSkillError as e:
            log_event(log, "execute.get_orders.error", error=str(e))
            return []

        cancelled: list[str] = []
        for o in payload.get("orders", []):
            status = str(o.get("status", "")).upper()
            oid = o.get("order_id")
            if not oid or status in terminal:
                continue
            try:
                run_skill(
                    "trade", "cancel_order",
                    "--order-id", str(oid),
                    "--acc-id", str(self.acc_id),
                    "--trd-env", self.trd_env,
                )
                cancelled.append(str(oid))
                log_event(log, "execute.cancelled", order_id=oid,
                          code=o.get("code"), status=status)
            except MoomooSkillError as e:
                log_event(log, "execute.cancel.error", order_id=oid, error=str(e))
        return cancelled

    def submit(self, orders: list[Order], dry_run: bool = False) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for order in orders:
            entry = order.as_dict() | {"trd_env": self.trd_env, "acc_id": self.acc_id}
            if dry_run:
                log_event(log, "execute.dry_run", **entry)
                results.append(entry | {"status": "dry_run"})
                continue
            try:
                payload = run_skill(
                    "trade", "place_order",
                    "--code", order.code,
                    "--side", order.side,
                    "--quantity", str(order.quantity),
                    "--price", f"{order.price}",
                    "--order-type", "NORMAL",
                    "--acc-id", str(self.acc_id),
                    "--trd-env", self.trd_env,
                )
            except MoomooSkillError as e:
                log_event(log, "execute.error", error=str(e), **entry)
                results.append(entry | {"status": "error", "error": str(e)})
                continue
            log_event(log, "execute.submitted", payload=payload, **entry)
            results.append(entry | {"status": "submitted", "order_id": payload.get("order_id")})
        return results
