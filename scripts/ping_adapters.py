from __future__ import annotations

import typer

from _bootstrap import ensure_src_path

ROOT = ensure_src_path()

from trading.adapters import build_router_from_config_dir  # noqa: E402
from trading.paths import resolve_paths  # noqa: E402

PATHS = resolve_paths(ROOT)

app = typer.Typer(add_completion=False)


@app.command()
def main(
    config_dir: str = typer.Option(
        str(PATHS.adapters),
        help="Adapter config directory",
    ),
) -> None:
    router = build_router_from_config_dir(config_dir)
    typer.echo(f"Loaded adapters: {', '.join(router.registered())}")
    typer.echo(str(router.ping_all()))


if __name__ == "__main__":
    app()
