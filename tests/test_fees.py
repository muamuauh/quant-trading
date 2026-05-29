"""Tests for the moomoo US-stock fee estimator."""

from __future__ import annotations

from pytest import approx

from qtf.execution.fees import estimate_us_fee, fee_as_bps


def test_buy_no_regulatory_fees():
    # BUY never incurs SEC / FINRA fees
    f = estimate_us_fee("BUY", 100, 50.0)
    assert f.sec_fee == 0.0
    assert f.finra_taf == 0.0


def test_sell_has_regulatory_fees():
    f = estimate_us_fee("SELL", 1000, 100.0)
    assert f.sec_fee > 0
    assert f.finra_taf > 0


def test_commission_minimum_applies():
    # 10 shares * $0.0049 = $0.049, below $0.99 min -> min kicks in
    f = estimate_us_fee("BUY", 10, 5.0)
    assert f.commission == approx(0.99)


def test_platform_minimum_applies():
    f = estimate_us_fee("BUY", 10, 5.0)
    assert f.platform_fee == approx(1.00)


def test_per_share_above_minimum():
    # 1000 shares: commission 1000*0.0049=4.90 > 0.99 min
    f = estimate_us_fee("BUY", 1000, 50.0)
    assert f.commission == approx(4.90)
    assert f.platform_fee == approx(5.00)  # 1000*0.005


def test_commission_capped_at_half_pct():
    # Cheap stock, large share count where 0.5% cap binds ABOVE the $0.99 floor.
    # 2000 sh * $0.50 = $1000 amount; per-share comm = 2000*0.0049 = $9.80;
    # 0.5% cap = $5.00; floor $0.99 -> min(9.80, 5.00)=5.00, max(5.00,0.99)=5.00
    f = estimate_us_fee("BUY", 2000, 0.50)
    assert f.commission == approx(5.00)


def test_floor_wins_over_cap_on_tiny_order():
    # $50 order: 0.5% cap = $0.25 < $0.99 floor -> floor wins
    f = estimate_us_fee("BUY", 10, 5.0)
    assert f.commission == approx(0.99)


def test_finra_taf_capped():
    # huge share count: TAF caps at $8.30
    f = estimate_us_fee("SELL", 1_000_000, 10.0)
    assert f.finra_taf == approx(8.30)


def test_sec_fee_scales_with_amount():
    f = estimate_us_fee("SELL", 1000, 100.0)  # amount = 100_000
    assert f.sec_fee == approx(0.0000278 * 100_000)


def test_total_is_sum():
    f = estimate_us_fee("SELL", 1000, 100.0)
    assert f.total == approx(f.commission + f.platform_fee + f.sec_fee + f.finra_taf)


def test_fee_as_bps_reasonable():
    # large-cap trade should be well under 1 bp
    bps = fee_as_bps("BUY", 958, 313.53)
    assert 0 < bps < 1.0


def test_zero_price_safe():
    f = estimate_us_fee("BUY", 0, 0.0)
    assert f.trade_amount == 0.0
    assert fee_as_bps("BUY", 0, 0.0) == 0.0
