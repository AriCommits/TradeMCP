"""Partitioned Parquet persistence and DuckDB analysis helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from trading.options.contracts import OptionContract
from .records import RawOptionQuoteRecord


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class OptionsParquetStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def write_contracts(self, contracts: Iterable[OptionContract]) -> list[Path]:
        rows = []
        for contract in contracts:
            row = contract.to_dict()
            row["expiration_year"] = contract.expiration_date.year
            rows.append(row)
        return self._write_parts("contracts", rows, ("underlying", "expiration_year"))

    def write_quotes(self, underlying: str, records: Iterable[RawOptionQuoteRecord]) -> list[Path]:
        rows = [
            {
                "underlying": underlying,
                "contract_id": r.contract_id,
                "as_of_utc": r.as_of_utc,
                "session_date": r.as_of_utc.date().isoformat(),
                "bid": r.bid,
                "ask": r.ask,
                "bid_size": r.bid_size,
                "ask_size": r.ask_size,
                "underlying_price": r.underlying_price,
                "source": r.source,
                "ingested_at_utc": r.ingested_at_utc,
                "last": r.last,
                "last_size": r.last_size,
                "source_record_id": r.source_record_id,
                "provider_fields": _json(r.provider_fields),
                "internal_fields": _json(r.internal_fields),
            }
            for r in records
        ]
        return self._write_parts("quotes", rows, ("underlying", "session_date"))

    def _write_parts(
        self, table: str, rows: list[dict[str, Any]], partitions: tuple[str, ...]
    ) -> list[Path]:
        if not rows:
            return []
        frame = pd.DataFrame(rows)
        paths: list[Path] = []
        for keys, group in frame.groupby(list(partitions), sort=True, dropna=False):
            values = keys if isinstance(keys, tuple) else (keys,)
            directory = self.root / table
            for name, value in zip(partitions, values):
                directory /= f"{name}={value}"
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f"part-{len(list(directory.glob('part-*.parquet'))):05d}.parquet"
            group.drop(columns=list(partitions)).to_parquet(target, index=False)
            paths.append(target)
        return paths


class OptionsQueryEngine:
    def __init__(self, root: str | Path) -> None:
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("DuckDB support requires the 'duckdb' package") from exc
        self._connection = duckdb.connect(database=":memory:")
        root_path = Path(root).resolve().as_posix().replace("'", "''")
        for table in ("contracts", "quotes"):
            pattern = f"{root_path}/{table}/**/*.parquet"
            self._connection.execute(
                f"CREATE VIEW {table} AS SELECT * FROM "
                f"read_parquet('{pattern}', hive_partitioning=true)"
            )

    def query(self, sql: str, parameters: list[Any] | None = None) -> pd.DataFrame:
        return self._connection.execute(sql, parameters or []).fetchdf()

    def close(self) -> None:
        self._connection.close()
