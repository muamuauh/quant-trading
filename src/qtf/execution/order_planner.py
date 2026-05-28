"""Diff target weights vs current positions → concrete buy/sell limit orders."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import floor


@dataclass
class Order:
    code: str           # US.AAPL
    side: str           # BUY | SELL
    quantity: int       # whole shares (US lot size = 1)
    price: float        # limit price
    reason: str         # human-readable why

    def as_dict(self) -> dict:
        return asdict(self)


def _round_us_price(px: float) -> float:
    """Round to the precision moomoo's place_order accepts for US stocks.

    NMS Rule 612 sub-penny pricing: stocks >= $1 quote in $0.01 (2 decimals),
    stocks < $1 quote in $0.0001 (4 decimals). moomoo enforces this strictly --
    submitting 4 decimals for a $300 stock is rejected as
    "下单接口价格参数精度不符合规范".
    """
    if px < 1.0:
        return round(px, 4)
    return round(px, 2)


def plan_orders(
    target_weights: dict[str, float],
    current_qty: dict[str, float],
    last_close: dict[str, float],
    total_equity: float,
    buy_slippage: float = 0.002,
    sell_slippage: float = 0.002,
) -> list[Order]:
    """Compute the list of orders that moves current → target.

    Algorithm (intentionally simple):
      - Target qty per ticker = floor(target_weight * total_equity / last_close).
      - If target > current → BUY the diff at last_close * (1 + buy_slippage).
      - If target < current → SELL the diff at last_close * (1 - sell_slippage).
      - Tickers not in target_weights are reduced to qty=0 if currently held.
      - Prices rounded per NMS Rule 612 (see `_round_us_price`).
    """
    orders: list[Order] = []
    universe = set(target_weights) | set(current_qty)

    for code in sorted(universe):
        target_w = target_weights.get(code, 0.0)
        cur_qty = int(current_qty.get(code, 0))
        px = last_close.get(code)
        if px is None or px <= 0:
            if cur_qty > 0:
                continue  # missing price; skip rather than guess
            continue
        target_qty = floor(target_w * total_equity / px) if target_w > 0 else 0
        diff = target_qty - cur_qty
        if diff > 0:
            orders.append(Order(
                code=code, side="BUY", quantity=diff,
                price=_round_us_price(px * (1 + buy_slippage)),
                reason=f"target_w={target_w:.3f} → qty {cur_qty}→{target_qty}",
            ))
        elif diff < 0:
            orders.append(Order(
                code=code, side="SELL", quantity=-diff,
                price=_round_us_price(px * (1 - sell_slippage)),
                reason=f"target_w={target_w:.3f} → qty {cur_qty}→{target_qty}",
            ))
    return orders
