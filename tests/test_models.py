import pytest
from src.trading.models.core import (
    AssetClass,
    LiquidityTier,
    AssetProfile,
    OrderType,
    OrderSide,
    OrderState,
    OrderConfig,
    OrderResult,
)
from datetime import datetime, timezone

def test_asset_profile():
    profile = AssetProfile(
        symbol="AAPL",
        asset_class=AssetClass.STOCK,
        liquidity_tier=LiquidityTier.BLUE_CHIP,
        typical_spread=0.01,
        avg_daily_volume=50000000.0,
    )
    assert profile.symbol == "AAPL"
    assert profile.asset_class == "stock"
    assert profile.liquidity_tier == "blue_chip"

def test_order_config():
    config = OrderConfig(
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        quantity=100.0,
        time_in_force="GTC",
        price=150.0,
    )
    assert config.order_type == "limit"
    assert config.side == "buy"
    assert config.price == 150.0

def test_order_result():
    result = OrderResult(
        order_id="12345",
        state=OrderState.PENDING,
        timestamp=datetime.now(timezone.utc)
    )
    assert result.state == "PENDING"
    assert result.order_id == "12345"
