"""TradingAgents review layer: per-candidate Buy/Hold/Sell call.

Pipeline placement: qlib's `topk_equal_weight` produces target weights →
`review_candidates` keeps only those rated at or above `min_rating` →
existing risk gates run on the filtered set → executor submits.

Each ticker triggers a full multi-agent run (~12 LLM calls), so this layer
is opt-in via `QTF_AGENTS_ENABLED=1`. Failures default to fail-open (the
candidate is kept) so an LLM outage doesn't block qlib-derived orders.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from qtf.agents.ticker_map import moomoo_to_yf
from qtf.config import settings
from qtf.utils.logging import get_logger, log_event


log = get_logger(__name__)


# Five-tier rating with descending bullishness; index = rank
_RATINGS = ["Buy", "Overweight", "Hold", "Underweight", "Sell"]


def _rank(rating: str) -> int:
    """Lower index = more bullish. Unknown ratings rank lowest (most bearish)."""
    norm = (rating or "").strip().title()
    if norm in _RATINGS:
        return _RATINGS.index(norm)
    return len(_RATINGS)  # unknown → most bearish


@dataclass
class ReviewVerdict:
    code: str
    rating: str
    rationale: str
    kept: bool
    error: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _build_graph():
    """Lazy import + construct TradingAgentsGraph (avoids LangGraph cost on import)."""
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    # DEFAULT_CONFIG already reads TRADINGAGENTS_* env vars
    return TradingAgentsGraph(debug=False, config=DEFAULT_CONFIG.copy())


def review_candidates(
    target_weights: dict[str, float],
    trade_date: date | None = None,
    min_rating: str | None = None,
    fail_open: bool | None = None,
) -> tuple[dict[str, float], list[ReviewVerdict]]:
    """Run TradingAgents on each candidate; return (kept_weights, all_verdicts)."""
    if not target_weights:
        return {}, []

    min_rating = min_rating or settings.qtf_agents_min_rating
    fail_open = bool(settings.qtf_agents_fail_open) if fail_open is None else fail_open
    trade_date = trade_date or date.today()
    cutoff = _rank(min_rating)

    log_event(log, "agents.review.start",
              candidates=list(target_weights.keys()),
              trade_date=str(trade_date),
              min_rating=min_rating,
              fail_open=fail_open)

    try:
        graph = _build_graph()
    except Exception as e:  # noqa: BLE001 — provider missing / no key etc.
        log_event(log, "agents.review.graph_init_error", error=str(e))
        if fail_open:
            verdicts = [ReviewVerdict(code, "Unknown", "graph init failed", True, str(e))
                        for code in target_weights]
            return dict(target_weights), verdicts
        return {}, [ReviewVerdict(c, "Unknown", "graph init failed", False, str(e))
                    for c in target_weights]

    verdicts: list[ReviewVerdict] = []
    kept_weights: dict[str, float] = {}
    for code in target_weights:
        yf_ticker = moomoo_to_yf(code)
        try:
            state, rating = graph.propagate(yf_ticker, trade_date.isoformat())
            rationale = state.get("final_trade_decision", "") if isinstance(state, dict) else ""
            keep = _rank(rating) <= cutoff
            verdicts.append(ReviewVerdict(code, rating, rationale, keep))
            log_event(log, "agents.review.verdict",
                      code=code, ticker=yf_ticker, rating=rating, kept=keep)
            if keep:
                kept_weights[code] = target_weights[code]
        except Exception as e:  # noqa: BLE001 — keep pipeline alive on any agent error
            log_event(log, "agents.review.error", code=code, ticker=yf_ticker, error=str(e))
            kept = fail_open
            verdicts.append(ReviewVerdict(code, "Error", "", kept, str(e)))
            if kept:
                kept_weights[code] = target_weights[code]

    log_event(log, "agents.review.done",
              kept=list(kept_weights.keys()),
              dropped=[v.code for v in verdicts if not v.kept])
    return kept_weights, verdicts
