from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import typer
from bs4 import BeautifulSoup

app = typer.Typer(add_completion=False)


def _fetch_finviz_news(ticker: str) -> tuple[str, list[dict[str, str]]]:
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", {"id": "news-table"})
    rows: list[dict[str, str]] = []

    if table is not None:
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            dt = tds[0].get_text(strip=True)
            a = tds[1].find("a")
            headline = a.get_text(strip=True) if a else tds[1].get_text(strip=True)
            href = a.get("href") if a else ""
            rows.append(
                {
                    "ticker": ticker,
                    "datetime_text": dt,
                    "headline": headline,
                    "url": href,
                }
            )

    return r.text, rows


@app.command()
def main(
    tickers: list[str] = typer.Option(["AAPL", "MSFT", "NVDA"], help="Tickers to scrape"),
    out_dir: str = typer.Option(
        "/Users/arian/Downloads/Trading/downloads_misc",
        help="Directory for raw HTML + parsed CSV outputs",
    ),
) -> None:
    base = Path(out_dir)
    raw_dir = base / "raw_html"
    parsed_dir = base / "parsed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict[str, str]] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for ticker in tickers:
        html, rows = _fetch_finviz_news(ticker.upper())
        (raw_dir / f"{ticker.upper()}_{stamp}.html").write_text(html, encoding="utf-8")
        all_rows.extend(rows)

    parsed_path = parsed_dir / f"finviz_headlines_{stamp}.csv"
    pd.DataFrame(all_rows).to_csv(parsed_path, index=False)
    typer.echo(f"Saved {len(all_rows)} rows to {parsed_path}")
    typer.echo(f"Raw files in {raw_dir}")


if __name__ == "__main__":
    app()
