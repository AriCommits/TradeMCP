from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import typer

from _bootstrap import ensure_src_path

ROOT = ensure_src_path()

from trading.backtest import run_pipeline  # noqa: E402
from trading.config import load_config  # noqa: E402
from trading.data_ingestion import read_ohlcv  # noqa: E402
from trading.metadata import build_run_metadata  # noqa: E402
from trading.paths import resolve_paths  # noqa: E402

PATHS = resolve_paths(ROOT)
MPL_CACHE = PATHS.downloads_misc / "mplcache"
MPL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE))

app = typer.Typer(add_completion=False)


@app.command()
def main(
    config: str = typer.Option(str(PATHS.markets / "stocks_base.yaml"), help="Path to YAML config"),
    input: str = typer.Option(str(PATHS.data / "sample_ohlcv.csv"), help="Input OHLCV CSV/Parquet"),
    output: str = typer.Option(str(PATHS.artifacts), help="Output artifact directory"),
    run_id: str | None = typer.Option(None, help="Optional run ID"),
    user_meta_json: str = typer.Option("{}", help="JSON object with user-defined metadata fields"),
) -> None:
    cfg = load_config(config).raw
    ohlcv = read_ohlcv(input)
    seed = int(cfg.get("seed", 42))

    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    try:
        user_meta = json.loads(user_meta_json)
        if not isinstance(user_meta, dict):
            raise ValueError("user_meta_json must decode to an object")
    except Exception as exc:
        raise typer.BadParameter(f"Invalid user_meta_json: {exc}") from exc

    metadata = build_run_metadata(
        config=cfg,
        seed=seed,
        config_path=config,
        run_id=run_id,
        command=" ".join(sys.argv),
        user_meta=user_meta,
        repo_root=PATHS.repo_root,
    )
    run_pipeline(ohlcv, cfg, output_dir=out, run_metadata=metadata)
    typer.echo(f"Pipeline complete. Artifacts in {out.resolve()}")


if __name__ == "__main__":
    app()
