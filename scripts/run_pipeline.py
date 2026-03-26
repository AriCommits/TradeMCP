from __future__ import annotations

import os
from pathlib import Path
import sys

import typer

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
MPL_CACHE = ROOT / "downloads_misc" / "mplcache"
MPL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE))

from trading.backtest import run_pipeline
from trading.config import load_config
from trading.data_ingestion import read_ohlcv

app = typer.Typer(add_completion=False)


@app.command()
def main(
    config: str = typer.Option("config/markets/stocks_base.yaml", help="Path to YAML config"),
    input: str = typer.Option("data/sample_ohlcv.csv", help="Input OHLCV CSV/Parquet"),
    output: str = typer.Option("artifacts", help="Output artifact directory"),
) -> None:
    cfg = load_config(config).raw
    ohlcv = read_ohlcv(input)

    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    run_pipeline(ohlcv, cfg, output_dir=out)
    typer.echo(f"Pipeline complete. Artifacts in {out.resolve()}")


if __name__ == "__main__":
    app()
