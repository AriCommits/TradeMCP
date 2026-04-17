# Modular Quantitative Trading Pipeline

Python research + visualization stack with a Rust execution backend.

> Disclaimer: This repository was primarily built with generative AI assistance and then iteratively reviewed and refined by a human maintainer.

## Architecture

- `src/trading/models/core.py`: Core trade and execution object model (AssetProfile, ExecutionContext, OrderConfig, OrderState)
- `src/trading/router.py`: `ModelRouter` for two-tier cloud/local model orchestration
- `src/trading/db/schema.py`: Database schemas for Research and Execution workflows
- `src/trading/log_setup.py`: Structured JSON logging framework
- `src/trading/adapters/base.py`: `BrokerBase` abstract base class for API integration
- `django_mcp_toolkit/`: Django-based Options Greeks + Equity Visualization Toolkit (MCP Plugin)
- `src/trading/data_ingestion.py` (Module A): interpolation, log returns, robust scaling, parquet I/O
- `src/trading/regime.py` (Module B): PCA+ICA+UMAP embeddings, HDBSCAN clustering, VI stability
- `src/trading/volatility.py` (Module C): cluster factor extraction + GARCH/EWMA forward volatility
- `src/trading/forecasting.py` (Module D): forecaster abstraction + walk-forward evaluation
- `src/trading/risk.py` (Step 5): z-score normalization, volatility gating, inverse-vol sizing
- `backend/rust_exec_engine` (Module E backend): slippage and implementation shortfall guardrail
- `src/trading/execution_client.py`: Python to Rust bridge
- `src/trading/backtest.py`: end-to-end orchestration
- `src/trading/app.py`: Streamlit diagnostics frontend

## Quick start

```bash
cd <repo-root>
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Generate synthetic data:

```bash
python scripts/generate_sample_data.py --out data/sample_ohlcv.csv
```

Build Rust execution backend:

```bash
cd backend/rust_exec_engine
cargo build --release
cd <repo-root>
```

Run pipeline:

```bash
python scripts/run_pipeline.py --config config/markets/stocks_base.yaml --input data/sample_ohlcv.csv --output artifacts
```

Market-specific base configs:

- `config/markets/stocks_base.yaml`
- `config/markets/forex_base.yaml`
- `config/markets/crypto_base.yaml`
- `config/markets/intl_stocks_base.yaml`

Run frontend:

```bash
streamlit run src/trading/app.py
```

## Webscraping outputs

All webscrape byproducts are written under:

- `downloads_misc`

Run scraper:

```bash
python scripts/scrape_finviz.py --tickers AAPL MSFT NVDA
```

Integration template config:

- `config/integrations/integration_targets.yaml`
- Per-adapter configs in `config/integrations/adapters/`:
- `config/integrations/adapters/tradingview.yaml`
- `config/integrations/adapters/fidelity_active_trader.yaml`
- `config/integrations/adapters/robinhood_crypto.yaml`
- `config/integrations/adapters/gemini.yaml`
- `config/integrations/adapters/forex_com.yaml`

Market/API research notes:

- `docs/market_expansion_research.md`

Adapter routing (loose-coupling intermediary API):

- Adapter modules: `src/trading/adapters/`
- Router: `src/trading/adapters/broker_router.py`
- Ping utility: `python scripts/ping_adapters.py`

Architecture plans:

- `docs/architecture/arch_plan_01.md`

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0).

See the full license text in:

- `LICENSE`
