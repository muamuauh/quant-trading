"""Pre-trade fail-fast risk chain. Each gate returns (passed: bool, reason: str)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from qtf.config import settings
from qtf.execution.order_planner import Order
from qtf.risk.market_hours import is_us_rth_now


@dataclass
class GateResult:
    name: str
    passed: bool
    reason: str


def load_limits(path: Path | None = None) -> dict:
    p = path or settings.risk_limits_yaml
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def env_guard(limits: dict) -> GateResult:
    if settings.futu_trd_env == "SIMULATE":
        return GateResult("env_guard", True, "trd_env=SIMULATE")
    if not limits.get("allow_real_env", False):
        return GateResult("env_guard", False, "REAL requested but allow_real_env=false")
    if settings.i_confirm_real != 1:
        return GateResult("env_guard", False, "REAL requested but I_CONFIRM_REAL!=1")
    return GateResult("env_guard", True, "REAL trading explicitly confirmed")


def market_hours_guard(limits: dict) -> GateResult:
    if not limits.get("require_us_rth", True):
        return GateResult("market_hours_guard", True, "RTH check disabled")
    if is_us_rth_now():
        return GateResult("market_hours_guard", True, "within US RTH")
    return GateResult("market_hours_guard", False, "outside US RTH")


def max_position_guard(target_weights: dict[str, float], limits: dict) -> GateResult:
    cap = float(limits.get("max_position_pct", 1.0))
    for code, w in target_weights.items():
        if w > cap + 1e-9:
            return GateResult("max_position_guard", False, f"{code} weight {w:.3f} > cap {cap}")
    return GateResult("max_position_guard", True, f"max single weight under {cap}")


def min_cash_guard(
    orders: list[Order],
    current_cash: float,
    total_equity: float,
    limits: dict,
) -> GateResult:
    min_pct = float(limits.get("min_cash_buffer_pct", 0.0))
    post_cash = current_cash
    for o in orders:
        if o.side == "BUY":
            post_cash -= o.price * o.quantity
        else:
            post_cash += o.price * o.quantity
    floor_cash = total_equity * min_pct
    if post_cash < floor_cash:
        return GateResult(
            "min_cash_guard",
            False,
            f"post-trade cash {post_cash:.2f} < required {floor_cash:.2f}",
        )
    return GateResult("min_cash_guard", True, f"post-trade cash {post_cash:.2f} >= {floor_cash:.2f}")


def daily_loss_kill_switch(
    orders: list[Order],
    today_pnl: float,
    total_equity: float,
    limits: dict,
) -> GateResult:
    max_loss = float(limits.get("max_daily_loss_pct", 1.0))
    if total_equity <= 0:
        return GateResult("daily_loss_kill_switch", True, "no equity context")
    loss_pct = -today_pnl / total_equity
    has_buy = any(o.side == "BUY" for o in orders)
    if loss_pct > max_loss and has_buy:
        return GateResult(
            "daily_loss_kill_switch",
            False,
            f"today loss {loss_pct:.3%} > cap {max_loss:.3%}; BUYs blocked",
        )
    return GateResult("daily_loss_kill_switch", True, f"today PnL ok ({loss_pct:.3%})")


def run_all_gates(
    *,
    target_weights: dict[str, float],
    orders: list[Order],
    current_cash: float,
    total_equity: float,
    today_pnl: float,
    limits: dict | None = None,
) -> tuple[bool, list[GateResult]]:
    limits = limits or load_limits()
    results = [
        env_guard(limits),
        market_hours_guard(limits),
        max_position_guard(target_weights, limits),
        min_cash_guard(orders, current_cash, total_equity, limits),
        daily_loss_kill_switch(orders, today_pnl, total_equity, limits),
    ]
    ok = all(r.passed for r in results)
    return ok, results
