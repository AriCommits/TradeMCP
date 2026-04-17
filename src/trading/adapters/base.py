from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from src.trading.models.core import AssetClass, OrderConfig, OrderResult, OrderState

class BrokerBase(ABC):
    """
    Abstract Base Class for all broker and financial data API interactions.
    This decouples agent logic from any specific broker implementation.
    """

    @abstractmethod
    def get_quote(self, symbol: str, asset_class: AssetClass) -> Dict[str, Any]:
        """Returns normalized quote across stocks, crypto, forex, derivatives."""
        pass

    @abstractmethod
    def place_order(self, order_config: OrderConfig) -> OrderResult:
        """Accepts an OrderConfig object, returns OrderResult."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Returns success/failure with cancellation latency."""
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderState:
        """Returns OrderState enum."""
        pass

    @abstractmethod
    def get_account_balance(self) -> Dict[str, float]:
        """Returns available capital."""
        pass

    @abstractmethod
    def get_historical_data(self, symbol: str, timeframe: str, start: str, end: str) -> List[Dict[str, Any]]:
        """Returns normalized OHLCV data."""
        pass
