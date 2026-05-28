"""Tests for moomoo→qlib row mapping."""

from __future__ import annotations

from qtf.data.schema import code_from_symbol, moomoo_to_qlib_df, symbol_from_code


def test_symbol_roundtrip():
    assert symbol_from_code("US.AAPL") == "aapl"
    assert symbol_from_code("HK.00700") == "00700"
    assert code_from_symbol("aapl") == "US.AAPL"


def test_moomoo_to_qlib_basic():
    payload = {
        "code": "US.AAPL",
        "ktype": "1d",
        "data": [
            {"time": "2024-01-02 00:00:00", "open": 187.15, "high": 188.44,
             "low": 183.89, "close": 185.64, "volume": 82488700, "turnover": 1.5e10},
            {"time": "2024-01-03 00:00:00", "open": 184.22, "high": 185.88,
             "low": 183.43, "close": 184.25, "volume": 58414500, "turnover": 1.07e10},
        ],
    }
    df = moomoo_to_qlib_df("US.AAPL", payload)
    assert list(df.columns) == ["symbol", "date", "open", "close", "high", "low", "volume", "factor"]
    assert len(df) == 2
    assert df.iloc[0]["symbol"] == "aapl"
    assert df.iloc[0]["date"] == "2024-01-02"
    assert df.iloc[0]["factor"] == 1.0


def test_moomoo_to_qlib_empty():
    df = moomoo_to_qlib_df("US.AAPL", {"data": []})
    assert df.empty
    assert list(df.columns) == ["symbol", "date", "open", "close", "high", "low", "volume", "factor"]


def test_moomoo_to_qlib_dedup_and_sort():
    payload = {
        "code": "US.AAPL",
        "data": [
            {"time": "2024-01-03", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"time": "2024-01-02", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 2},
            {"time": "2024-01-02", "open": 3, "high": 3, "low": 3, "close": 3, "volume": 3},  # dup
        ],
    }
    df = moomoo_to_qlib_df("US.AAPL", payload)
    assert len(df) == 2
    assert df.iloc[0]["date"] == "2024-01-02"
    assert df.iloc[1]["date"] == "2024-01-03"
