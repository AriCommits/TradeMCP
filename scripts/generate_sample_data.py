from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import typer

app = typer.Typer(add_completion=False)


@app.command()
def main(
    out: str = typer.Option("data/sample_ohlcv.csv", help="Output CSV path"),
    symbols: str = typer.Option("AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AMD"),
    start: str = typer.Option("2020-01-01"),
    periods: int = typer.Option(1400),
    seed: int = typer.Option(42),
) -> None:
    rng = np.random.default_rng(seed)
    tickers = [s.strip() for s in symbols.split(",") if s.strip()]
    dates = pd.bdate_range(start=start, periods=periods)

    frames = []
    for i, sym in enumerate(tickers):
        drift = 0.0002 + (i * 0.00002)
        vol = 0.012 + (i % 4) * 0.002

        returns = drift + vol * rng.standard_normal(len(dates))
        price = 100.0 * np.exp(np.cumsum(returns))

        close = price
        open_ = close * (1 + 0.001 * rng.standard_normal(len(dates)))
        high = np.maximum(open_, close) * (1 + 0.002 * rng.random(len(dates)))
        low = np.minimum(open_, close) * (1 - 0.002 * rng.random(len(dates)))
        volume = rng.integers(500_000, 5_000_000, size=len(dates))

        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "symbol": sym,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
        )

    df = pd.concat(frames, ignore_index=True)
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    typer.echo(f"Wrote {len(df)} rows to {path.resolve()}")


if __name__ == "__main__":
    app()
