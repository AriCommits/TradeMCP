from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime


class AssetClass(str, Enum):
    STOCK = "stock"
    CRYPTO = "crypto"
    FOREX = "forex"
    DERIVATIVE = "derivative"


class LiquidityTier(str, Enum):
    BLUE_CHIP = "blue_chip"
    MID_CAP = "mid_cap"
    SMALL_CAP = "small_cap"
    PENNY = "penny"
    MAJOR_PAIR = "major_pair"
    ALTCOIN = "altcoin"
    OTHER = "other"


@dataclass
class AssetProfile:
    symbol: str
    asset_class: AssetClass
    liquidity_tier: LiquidityTier
    typical_spread: float
    avg_daily_volume: float


@dataclass
class ResearchConfig:
    model_id: str
    model_type: str
    hyperparameters: Dict[str, Any]
    timeframe: str
    entry_signal_threshold: float
    confidence_score: float
    asset_profile: AssetProfile


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderState(str, Enum):
    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELED = "CANCELED"
    CANCELLATION_PENDING = "CANCELLATION_PENDING"


@dataclass
class ExecutionContext:
    model_id: str
    execution_batch_id: str
    order_type: OrderType
    position_size: float
    slippage_model: str
    fee_estimate: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    execution_window: str


@dataclass
class OrderConfig:
    order_type: OrderType
    side: OrderSide
    quantity: float
    time_in_force: str
    price: Optional[float] = None


@dataclass
class OrderResult:
    order_id: str
    state: OrderState
    timestamp: datetime
    fill_price: Optional[float] = None
    fill_quantity: float = 0.0
    slippage_actual: Optional[float] = None
    fee_actual: Optional[float] = None
