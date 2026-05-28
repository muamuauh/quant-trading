"""Tests for the TradingAgents review layer (mocked LLM)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from qtf.agents.review import review_candidates


def _stub_graph(rating_per_ticker):
    """Build a stub graph whose propagate(ticker, ...) returns `rating_per_ticker[ticker]`."""
    class _Stub:
        def propagate(self, ticker, trade_date, asset_type="stock"):  # noqa: ARG002
            rating = rating_per_ticker[ticker]
            if isinstance(rating, Exception):
                raise rating
            return {"final_trade_decision": f"Rating: {rating}"}, rating
    return _Stub()


def test_keeps_buy_and_overweight_drops_others():
    ratings = {"AAPL": "Buy", "MSFT": "Overweight", "NVDA": "Hold",
               "GOOGL": "Underweight", "TSLA": "Sell"}
    weights_in = {f"US.{t}": 0.2 for t in ratings}

    with patch("qtf.agents.review._build_graph", return_value=_stub_graph(ratings)):
        kept, verdicts = review_candidates(weights_in, trade_date=date(2026, 5, 23),
                                            min_rating="Overweight")

    assert set(kept) == {"US.AAPL", "US.MSFT"}
    assert len(verdicts) == 5
    kept_by_code = {v.code: v.kept for v in verdicts}
    assert kept_by_code == {
        "US.AAPL": True, "US.MSFT": True,
        "US.NVDA": False, "US.GOOGL": False, "US.TSLA": False,
    }


def test_strict_min_rating_only_buy():
    ratings = {"AAPL": "Buy", "MSFT": "Overweight"}
    weights_in = {"US.AAPL": 0.5, "US.MSFT": 0.5}

    with patch("qtf.agents.review._build_graph", return_value=_stub_graph(ratings)):
        kept, _ = review_candidates(weights_in, trade_date=date(2026, 5, 23),
                                     min_rating="Buy")

    assert set(kept) == {"US.AAPL"}


def test_fail_open_keeps_candidate_on_error():
    ratings = {"AAPL": "Buy", "MSFT": RuntimeError("api down")}
    weights_in = {"US.AAPL": 0.5, "US.MSFT": 0.5}

    with patch("qtf.agents.review._build_graph", return_value=_stub_graph(ratings)):
        kept, verdicts = review_candidates(weights_in, trade_date=date(2026, 5, 23),
                                            min_rating="Overweight", fail_open=True)

    assert set(kept) == {"US.AAPL", "US.MSFT"}  # error → kept under fail-open
    err = next(v for v in verdicts if v.code == "US.MSFT")
    assert err.error and "api down" in err.error


def test_fail_closed_drops_candidate_on_error():
    ratings = {"AAPL": "Buy", "MSFT": RuntimeError("api down")}
    weights_in = {"US.AAPL": 0.5, "US.MSFT": 0.5}

    with patch("qtf.agents.review._build_graph", return_value=_stub_graph(ratings)):
        kept, _ = review_candidates(weights_in, trade_date=date(2026, 5, 23),
                                     min_rating="Overweight", fail_open=False)

    assert set(kept) == {"US.AAPL"}


def test_empty_weights_short_circuits():
    kept, verdicts = review_candidates({}, trade_date=date(2026, 5, 23))
    assert kept == {}
    assert verdicts == []


def test_graph_init_failure_fail_open():
    def _raise():
        raise RuntimeError("OPENAI_API_KEY not set")

    weights_in = {"US.AAPL": 0.5}
    with patch("qtf.agents.review._build_graph", side_effect=_raise):
        kept, verdicts = review_candidates(weights_in, fail_open=True)
    assert kept == weights_in
    assert verdicts[0].error and "OPENAI_API_KEY" in verdicts[0].error
