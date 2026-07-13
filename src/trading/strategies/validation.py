"""Parameter and identity validation for strategy plug-ins."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any


_VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class ParameterKind(str, Enum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"


@dataclass(frozen=True)
class ParameterField:
    """One dependency-free, JSON-compatible strategy parameter declaration."""

    kind: ParameterKind
    required: bool = True
    default: bool | int | float | str | None = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[bool | int | float | str, ...] = ()

    def __post_init__(self) -> None:
        if self.minimum is not None and not isfinite(self.minimum):
            raise ValueError("minimum must be finite")
        if self.maximum is not None and not isfinite(self.maximum):
            raise ValueError("maximum must be finite")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        if self.required and self.default is not None:
            raise ValueError("required parameters cannot declare a default")
        if self.default is not None:
            self.validate(self.default, field_name="default")
        for choice in self.choices:
            self.validate(choice, field_name="choice")

    def validate(self, value: Any, *, field_name: str) -> None:
        valid = False
        if self.kind is ParameterKind.BOOLEAN:
            valid = isinstance(value, bool)
        elif self.kind is ParameterKind.INTEGER:
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif self.kind is ParameterKind.NUMBER:
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
            valid = valid and isfinite(float(value))
        elif self.kind is ParameterKind.STRING:
            valid = isinstance(value, str)
        if not valid:
            raise ValueError(f"{field_name} must be {self.kind.value}")
        if self.choices and value not in self.choices:
            raise ValueError(f"{field_name} must be one of {self.choices!r}")
        if self.kind in {ParameterKind.INTEGER, ParameterKind.NUMBER}:
            numeric = float(value)
            if self.minimum is not None and numeric < self.minimum:
                raise ValueError(f"{field_name} must be >= {self.minimum}")
            if self.maximum is not None and numeric > self.maximum:
                raise ValueError(f"{field_name} must be <= {self.maximum}")


@dataclass(frozen=True)
class ParameterSchema:
    """A strict parameter schema whose normalized output has stable key ordering."""

    schema_version: str
    fields: Mapping[str, ParameterField]
    allow_unknown: bool = False

    def __post_init__(self) -> None:
        validate_version(self.schema_version, field_name="parameter schema version")
        invalid = [name for name in self.fields if not _IDENTIFIER_PATTERN.fullmatch(name)]
        if invalid:
            raise ValueError(f"invalid parameter names: {sorted(invalid)!r}")

    def validate(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(parameters).difference(self.fields))
        if unknown and not self.allow_unknown:
            raise ValueError(f"unknown strategy parameters: {unknown!r}")
        normalized: dict[str, Any] = {}
        for name in sorted(self.fields):
            field = self.fields[name]
            if name in parameters:
                value = parameters[name]
            elif field.required:
                raise ValueError(f"missing required strategy parameter: {name}")
            else:
                value = field.default
            if value is not None:
                field.validate(value, field_name=name)
                normalized[name] = value
        if self.allow_unknown:
            for name in unknown:
                normalized[name] = parameters[name]
        return normalized


def validate_version(value: str, *, field_name: str = "version") -> tuple[int, int, int]:
    """Validate the platform's deliberately narrow ``major.minor.patch`` format."""

    match = _VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"{field_name} must use major.minor.patch numeric format")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def validate_strategy_id(value: str) -> None:
    if _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError("strategy_id must be lowercase snake_case")
