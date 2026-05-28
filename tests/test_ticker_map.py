"""Tests for moomoo ↔ yfinance ticker conversion."""

from __future__ import annotations

from qtf.agents.ticker_map import moomoo_to_yf


def test_us_strip_prefix():
    assert moomoo_to_yf("US.AAPL") == "AAPL"
    assert moomoo_to_yf("US.NVDA") == "NVDA"


def test_hk_zero_pad():
    assert moomoo_to_yf("HK.00700") == "0700.HK"
    assert moomoo_to_yf("HK.09988") == "9988.HK"


def test_cn_a_share():
    assert moomoo_to_yf("SH.601318") == "601318.SS"
    assert moomoo_to_yf("SZ.000001") == "000001.SZ"


def test_unknown_prefix_passthrough():
    assert moomoo_to_yf("XYZ.FOO") == "XYZ.FOO"


def test_no_dot_passthrough():
    assert moomoo_to_yf("AAPL") == "AAPL"
