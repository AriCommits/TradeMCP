"""Standalone adapter implementations per venue/platform (no shared inheritance)."""

from .broker_router import BrokerRouter, build_router_from_config_dir
from .fidelity_active_trader_adapter import FidelityActiveTraderAdapter, FidelityActiveTraderConfig
from .forex_com_adapter import ForexComAdapter, ForexComConfig
from .gemini_adapter import GeminiAdapter, GeminiConfig
from .protocols import AdapterExecutionProtocol, AdapterProtocol, AdapterReadProtocol
from .robinhood_crypto_adapter import RobinhoodCryptoAdapter, RobinhoodCryptoConfig
from .tradingview_adapter import TradingViewAdapter, TradingViewConfig

__all__ = [
    "BrokerRouter",
    "build_router_from_config_dir",
    "TradingViewAdapter",
    "TradingViewConfig",
    "FidelityActiveTraderAdapter",
    "FidelityActiveTraderConfig",
    "RobinhoodCryptoAdapter",
    "RobinhoodCryptoConfig",
    "GeminiAdapter",
    "GeminiConfig",
    "ForexComAdapter",
    "ForexComConfig",
    "AdapterReadProtocol",
    "AdapterExecutionProtocol",
    "AdapterProtocol",
]
