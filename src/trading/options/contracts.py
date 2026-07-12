"""Versioned option contracts and shared time/serialization semantics.

Unit conventions for schema version 1:

* timestamps are timezone-aware UTC instants;
* ``session_date`` is the exchange-local trading-session label, not UTC date;
* money and prices are decimal currency units per share unless named otherwise;
* multiplier is deliverable units per contract (normally 100 for US equity options);
* volatility and rates are annualized decimal fractions (``0.20`` means 20%);
* returns are decimal fractions; and Greeks are per one option share before multiplier.
"""

from __future__ import annotations

import json
import types
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar, TypeVar, Union, cast, get_args, get_origin, get_type_hints


SCHEMA_VERSION = "1.0"
RecordT = TypeVar("RecordT", bound="VersionedRecord")


def require_utc(value: datetime, field_name: str) -> None:
    """Reject naive or non-UTC timestamps instead of silently changing semantics."""
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{field_name} must be timezone-aware UTC")


def _encode_json(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        require_utc(value, "timestamp")
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, VersionedRecord):
        return value.to_dict()
    if is_dataclass(value):
        return {field.name: _encode_json(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _encode_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_encode_json(item) for item in value]
    return value


def _decode_json(annotation: Any, value: Any) -> Any:
    if value is None:
        return None
    if annotation is Any:
        return value

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (Union, types.UnionType):
        candidates = [candidate for candidate in args if candidate is not type(None)]
        if len(candidates) == 1:
            return _decode_json(candidates[0], value)
        for candidate in candidates:
            try:
                return _decode_json(candidate, value)
            except (TypeError, ValueError):
                continue
        return value
    if origin in (tuple, list):
        item_type = args[0] if args else Any
        decoded = [_decode_json(item_type, item) for item in value]
        return tuple(decoded) if origin is tuple else decoded
    if origin in (dict, Mapping):
        key_type, value_type = args if len(args) == 2 else (Any, Any)
        return {
            _decode_json(key_type, key): _decode_json(value_type, item)
            for key, item in value.items()
        }
    if annotation is datetime:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        require_utc(parsed, "timestamp")
        return parsed
    if annotation is date:
        return date.fromisoformat(str(value))
    if annotation is Decimal:
        return Decimal(str(value))
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if isinstance(annotation, type) and issubclass(annotation, VersionedRecord):
        return annotation.from_dict(value)
    return value


class VersionedRecord:
    """Mixin providing deterministic JSON-friendly serialization."""

    schema_version: ClassVar[str] = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        if not is_dataclass(self):
            raise TypeError("VersionedRecord subclasses must be dataclasses")
        payload = {
            field.name: _encode_json(getattr(self, field.name))
            for field in fields(self)
            if field.init
        }
        return {"schema_version": self.schema_version, **payload}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls: type[RecordT], payload: Mapping[str, Any]) -> RecordT:
        version = payload.get("schema_version")
        if version != cls.schema_version:
            raise ValueError(
                f"unsupported {cls.__name__} schema_version {version!r}; "
                f"expected {cls.schema_version!r}"
            )
        hints = get_type_hints(cls)
        values: dict[str, Any] = {}
        for field in fields(cast(Any, cls)):
            if field.init and field.name in payload:
                values[field.name] = _decode_json(hints[field.name], payload[field.name])
        return cls(**values)

    @classmethod
    def from_json(cls: type[RecordT], payload: str) -> RecordT:
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise ValueError(f"serialized {cls.__name__} must be a JSON object")
        return cls.from_dict(decoded)


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class ExerciseStyle(str, Enum):
    AMERICAN = "american"
    EUROPEAN = "european"


class SettlementType(str, Enum):
    PHYSICAL = "physical"
    CASH = "cash"


class LegSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class TimeHorizonKind(str, Enum):
    """Clock used by a forecast or holding period."""

    CALENDAR_DAYS = "calendar_days"
    TRADING_DAYS = "trading_days"
    OVERNIGHT_INTERVALS = "overnight_intervals"
    EXPIRATION_TIMESTAMP = "expiration_timestamp"


@dataclass(frozen=True)
class TimeHorizon(VersionedRecord):
    """A horizon with explicit calendar/exchange semantics.

    Count-based horizons use ``count``. Expiration horizons use the exact
    exchange-defined ``end_at_utc`` instant. These representations are deliberately
    not interchangeable.
    """

    kind: TimeHorizonKind
    count: int | None = None
    end_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        if self.kind is TimeHorizonKind.EXPIRATION_TIMESTAMP:
            if self.end_at_utc is None or self.count is not None:
                raise ValueError("expiration_timestamp requires end_at_utc and no count")
            require_utc(self.end_at_utc, "end_at_utc")
        elif self.count is None or self.count <= 0 or self.end_at_utc is not None:
            raise ValueError("count-based horizons require a positive count and no end_at_utc")


@dataclass(frozen=True)
class Deliverable(VersionedRecord):
    asset_id: str
    quantity: Decimal
    asset_kind: str = "equity"

    def __post_init__(self) -> None:
        if not self.asset_id or self.quantity <= 0:
            raise ValueError("deliverable requires an asset_id and positive quantity")


@dataclass(frozen=True)
class OptionContract(VersionedRecord):
    contract_id: str
    occ_symbol: str
    underlying: str
    option_type: OptionType
    strike: Decimal
    expiration_date: date
    expiration_at_utc: datetime
    exercise_style: ExerciseStyle
    settlement_type: SettlementType
    multiplier: Decimal = Decimal("100")
    currency: str = "USD"
    listing_exchange: str | None = None
    deliverable: tuple[Deliverable, ...] = ()

    def __post_init__(self) -> None:
        require_utc(self.expiration_at_utc, "expiration_at_utc")
        if not self.contract_id or not self.occ_symbol or not self.underlying:
            raise ValueError("contract identifiers and underlying are required")
        if self.strike <= 0 or self.multiplier <= 0:
            raise ValueError("strike and multiplier must be positive")
        if len(self.currency) != 3 or self.currency.upper() != self.currency:
            raise ValueError("currency must be an uppercase ISO-style code")


@dataclass(frozen=True)
class OptionLeg(VersionedRecord):
    contract: OptionContract
    side: LegSide
    quantity: int
    limit_price: Decimal | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("leg quantity must be a positive contract count")
        if self.limit_price is not None and self.limit_price < 0:
            raise ValueError("limit_price cannot be negative")


@dataclass(frozen=True)
class OptionPosition(VersionedRecord):
    position_id: str
    leg: OptionLeg
    opened_at_utc: datetime
    average_open_price: Decimal

    def __post_init__(self) -> None:
        require_utc(self.opened_at_utc, "opened_at_utc")
        if not self.position_id or self.average_open_price < 0:
            raise ValueError("position_id is required and average_open_price cannot be negative")
