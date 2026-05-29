"""moomoo US-stock fee estimator.

moomoo's paper account does not return real fees (get_order_fee.py replies
"暂时不支持模拟交易"), so we model them from moomoo Financial Inc.'s published
US-equity schedule. Rates are pass-through where noted and change over time --
update the constants here if moomoo revises them.

Published schedule (as of 2024-2025, moomoo Financial Inc. standard tier):

  Commission     : $0.0049 / share, min $0.99 / order, max 0.5% of trade value
  Platform fee   : $0.005  / share, min $1.00 / order
  Regulatory fees (third-party, pass-through, SELL only):
    SEC fee      : $0.0000278 x trade amount      (rate set by SEC, varies)
    FINRA TAF    : $0.000166 / share, max $8.30   (rate set by FINRA)

Reference: https://www.moomoo.com/us/support/topic3_438
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


# --- moomoo US-equity rate constants (edit if moomoo revises) ---
COMMISSION_PER_SHARE = 0.0049
COMMISSION_MIN = 0.99
COMMISSION_MAX_PCT = 0.005           # cap at 0.5% of trade value

PLATFORM_PER_SHARE = 0.005
PLATFORM_MIN = 1.00

SEC_FEE_RATE = 0.0000278             # x trade amount, SELL only
FINRA_TAF_PER_SHARE = 0.000166       # SELL only
FINRA_TAF_MAX = 8.30


@dataclass
class FeeBreakdown:
    commission: float
    platform_fee: float
    sec_fee: float        # SELL only, else 0
    finra_taf: float      # SELL only, else 0
    total: float
    trade_amount: float

    def as_dict(self) -> dict:
        return asdict(self)


def estimate_us_fee(side: str, qty: float, price: float) -> FeeBreakdown:
    """Estimate moomoo US-stock fees for one order.

    `side`: "BUY" or "SELL" (case-insensitive). SELL adds SEC + FINRA fees.
    """
    qty = abs(float(qty))
    amount = qty * float(price)
    is_sell = str(side).strip().upper() == "SELL"

    # Cap the per-share commission at 0.5% of trade value first, then apply the
    # $0.99 floor. The floor always wins, so the 0.5% cap only bites on cheap
    # sub-$1 stocks with large share counts (where 0.5% still exceeds $0.99).
    commission = COMMISSION_PER_SHARE * qty
    if amount > 0:
        commission = min(commission, COMMISSION_MAX_PCT * amount)
    commission = max(commission, COMMISSION_MIN)

    platform = max(PLATFORM_MIN, PLATFORM_PER_SHARE * qty)

    sec = SEC_FEE_RATE * amount if is_sell else 0.0
    taf = min(FINRA_TAF_MAX, FINRA_TAF_PER_SHARE * qty) if is_sell else 0.0

    total = commission + platform + sec + taf
    return FeeBreakdown(
        commission=round(commission, 4),
        platform_fee=round(platform, 4),
        sec_fee=round(sec, 4),
        finra_taf=round(taf, 4),
        total=round(total, 4),
        trade_amount=round(amount, 2),
    )


def fee_as_bps(side: str, qty: float, price: float) -> float:
    """Total fee as basis points of trade amount (1 bp = 0.01%)."""
    fb = estimate_us_fee(side, qty, price)
    if fb.trade_amount <= 0:
        return 0.0
    return fb.total / fb.trade_amount * 1e4
