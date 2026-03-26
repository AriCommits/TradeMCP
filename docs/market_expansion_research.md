# Market Expansion Research and Integration Plan (2026-03-26)

## 1) Scope

You asked to extend this system beyond US equities and prepare for future general-use deployment across:
- Forex
- Crypto
- International equities
- UI/API integrations: TradingView, Fidelity Active Trader / Trader+, Robinhood, Gemini ActiveTrader, FOREX.com

## 2) What was implemented in this pass

- Config refactor to market profiles:
  - `config/markets/stocks_base.yaml` (moved from old `config/base.yaml`)
  - `config/markets/forex_base.yaml`
  - `config/markets/crypto_base.yaml`
  - `config/markets/intl_stocks_base.yaml`
- Default CLI config now points to `config/markets/stocks_base.yaml`.
- Added indicator extension layer:
  - `src/trading/indicators.py`
  - Native RSI/ATR/MACD support and config-driven inclusion in model features.
- Added integration template config:
  - `config/integrations/integration_targets.yaml`
  - `config/integrations/adapters/*.yaml` (one config per adapter)
- Added adapter layer:
  - `src/trading/adapters/` (standalone adapters)
  - `src/trading/adapters/broker_router.py` (loose-coupling intermediary API router)

## 3) Market strategy research (practical additions)

### Forex (24/5, macro + session structure)

Recommended strategy buckets:
- Session breakout + volatility filter (London/NY overlap).
- Trend/momentum on liquid majors, volatility-targeted sizing.
- Mean reversion on overextended intraday moves (only under low realized vol regime).

Pipeline additions for Forex:
- Session-aware features (hour bucket, overlap flags).
- Macro calendar/event shock flags (CPI/FOMC/NFP windows).
- Pair relationship features (USD basket, cross-pair residuals).

### Crypto (24/7, regime shifts + microstructure)

Recommended strategy buckets:
- Regime momentum with hard vol caps.
- Cross-exchange dislocation/funding or basis style mean reversion.
- Liquidity-aware breakout with stricter slippage guardrails.

Pipeline additions for Crypto:
- Weekend effect and 24/7 session features.
- Exchange/liquidity proxies and spread proxies.
- Dynamic risk throttles (faster rebalance than equities).

### International equities (multi-timezone + calendar fragmentation)

Recommended strategy buckets:
- Country/sector relative momentum (regional rotation).
- Vol-targeted mean reversion around local open/close windows.
- ADR/local-listing spread or index-vs-country ETF divergence.

Pipeline additions for International equities:
- Exchange-calendar aware alignment and holiday handling.
- Local-currency and FX-hedged return decomposition.
- Per-market execution assumptions (spread + depth by venue).

## 4) Integration research: platform feasibility

### TradingView

Feasibility: strong
- Webhook alerts support HTTP POST automation triggers.
- Broker Integration API exists for deeper order/trading integration.

Suggested use in this project:
- Phase 1: webhook signal ingress into Python order-intent queue.
- Phase 2: full broker integration only if you operate/partner a broker backend.

Sources:
- https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/
- https://my.tradingview.com/broker-api-docs/
- https://www.tradingview.com/broker-api-docs/endpoints/

### Fidelity Active Trader / Trader+

Feasibility: partial / constrained
- Fidelity documents Active Trader Pro / Trader+ as desktop/web/mobile trading platforms.
- I did not find a documented public retail order-entry API on Fidelity's platform docs.

Suggested use in this project:
- Phase 1: human-in-the-loop workflow (generate tickets/signals, execute manually).
- Phase 2: if Fidelity publishes official retail APIs, add official adapter.

Sources:
- https://www.fidelity.com/trading/trading-platforms
- https://www.fidelity.com/trading/advanced-trading-tools/active-trader-pro/faqs-desktop
- https://www.fidelity.com/customer-service/how-to-access-active-trader-pro

### Robinhood (Crypto)

Feasibility: strong for crypto
- Robinhood officially announced Crypto Trading API.
- Support docs indicate v1/v2 API model and credential workflow.

Suggested use in this project:
- Build crypto-only adapter first (read products/quotes/orders + place/cancel).
- Keep equities/options out of scope unless official API coverage expands.

Sources:
- https://robinhood.com/us/en/newsroom/robinhood-crypto-trading-api/
- https://robinhood.com/us/en/support/articles/crypto-api/?hcs=true
- https://docs.robinhood.com/crypto/trading/

### Gemini ActiveTrader / Gemini Exchange

Feasibility: strong
- Gemini documents REST + WebSocket + FIX connectivity and trading authentication.
- ActiveTrader UI positioning aligns with advanced strategy workflows.

Suggested use in this project:
- Build Gemini REST adapter for order lifecycle + WebSocket market/order events.
- Use sandbox/fast websocket channels for low-latency experiments.

Sources:
- https://support.gemini.com/hc/en-us/articles/204732875-How-can-I-use-the-Gemini-API
- https://docs.gemini.com/rest-api/
- https://docs.gemini.com/websocket-api/
- https://docs.gemini.com/websocket/authentication
- https://www.gemini.com/en-SG/activetrader

### FOREX.com

Feasibility: strong (account + enablement)
- FOREX.com markets an API trading path via REST API.
- Their API pages indicate account creation + service-team enablement for REST access; institutional FIX also available.

Suggested use in this project:
- Build FOREX.com REST adapter for forex order routing and account state.
- Request API enablement early to avoid timeline delays.

Sources:
- https://qa-web.forex.com/en-us/premium-trader-tools/api-trading/
- https://qa-web.forex.com/en/trading-tools/api-trading/
- https://qa-web.forex.com/en-us/

## 5) Library strategy: built-in vs external

Recommended approach: hybrid
- Keep core risk/execution gating and pipeline orchestration in your own code (control + auditability).
- Use vetted external libs for high-churn utilities.

Suggested external libraries:
- Exchange calendars/timezone correctness: `exchange_calendars`
  - https://pypi.org/project/exchange_calendars/
- Rust indicator acceleration (if/when moving indicator calc into Rust): `ta` crate
  - https://docs.rs/ta

Current implementation now supports config-driven indicators via native computations (RSI/ATR/MACD) and is ready to add optional third-party backends later.

## 6) Recommended next build order

1. Build normalized adapter interface (submit_order, cancel_order, positions, balances, quotes).
2. Implement Robinhood Crypto + Gemini adapters first (best documented API paths).
3. Add FOREX.com adapter next (post access enablement).
4. Add TradingView webhook ingress and order-intent validation service.
5. Keep Fidelity as manual/human-in-loop until official API path is available.
6. Add venue-specific execution models and slippage calibration per market.
