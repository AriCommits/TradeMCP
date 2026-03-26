from __future__ import annotations

from pathlib import Path
import sys

import typer

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading.adapters import build_router_from_config_dir  # noqa: E402

app = typer.Typer(add_completion=False)


@app.command()
def main(
    config_dir: str = typer.Option(
        "config/integrations/adapters",
        help="Adapter config directory",
    ),
) -> None:
    router = build_router_from_config_dir(config_dir)
    typer.echo(f"Loaded adapters: {', '.join(router.registered())}")
    typer.echo(str(router.ping_all()))


if __name__ == "__main__":
    app()
