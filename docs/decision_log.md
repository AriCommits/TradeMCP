# Cryptocurrency Movement Research Decision Log

**Status:** Fixture-only scaffolding is permitted. Full venue data collection is blocked.

The machine-enforced gate is derived from `config/crypto_movement/project.yaml`; a boolean cannot override unresolved decisions. A proxy venue may be proposed later, but no proxy is silently selected here.

| Decision | Status | Value | Source | As of | Notes |
|---|---|---|---|---|---|
| Analysis timezone | CONFIRMED | UTC | Project brief | 2026-08-01 | Canonical storage and folds use timezone-aware UTC. |
| Anchor semantics | CONFIRMED | Completed candle | Project brief | 2026-08-01 | The candle must be closed as of an explicit observation time. |
| Primary/ablation cadence | CONFIRMED | 15m / 30m | Project brief | 2026-08-01 | Both represent a 24-hour sequence. |
| Forecast horizons | CONFIRMED | 1h, 3h, 6h, 12h | Project brief | 2026-08-01 | Each horizon has separate outputs. |
| Arithmetic barrier | CONFIRMED | +/-4% | Project brief | 2026-08-01 | Log-space thresholds are log(1.04) and log(0.96). |
| Weekend feature policy | CONFIRMED | Excluded from primary training | Project brief | 2026-08-01 | Weekend analysis uses frozen predictions last. |
| Production venue and API | BLOCKING_FULL_DOWNLOAD | Unset | User required | 2026-08-01 | Exact prop venue is preferred; proxy research must be labeled. |
| Instrument, venue pair, quote | BLOCKING_FULL_DOWNLOAD | Unset | User required | 2026-08-01 | Spot versus perpetual must be explicit. |
| Candle boundaries and data coverage | BLOCKING_FULL_DOWNLOAD | Unset | User required | 2026-08-01 | Include rate limits, interval history, gap/relisting policy, and label-resolution data. |
| Fees, spread, slippage, funding | BLOCKING_FULL_DOWNLOAD | Unset | User required | 2026-08-01 | Funding may be marked not applicable for spot. |
| Prop drawdown mechanics | BLOCKING_FULL_DOWNLOAD | Unset | User required | 2026-08-01 | Trailing, intraday, and end-of-day rules must be confirmed or marked not applicable. |
| Point-in-time universe feasibility | BLOCKING_FULL_DOWNLOAD | Unset | User required | 2026-08-01 | Otherwise the survivor limitation must remain prominent. |
| Final lockbox dates | BLOCKING_FULL_DOWNLOAD | Unset | User required | 2026-08-01 | Freeze only after verified data coverage. |
| Gen-1 bundle location | BLOCKING_FULL_DOWNLOAD | Not present | Repository inspection | 2026-08-01 | Preserve `crypto_weekend_seasonality/` unchanged when supplied. |

## How to resolve a blocker

Update the corresponding decision with a concrete value, source, date, and rationale. Change the status to `CONFIRMED` only when the value is verified for the intended research instrument. `PROXY_ASSUMPTION` remains blocked for production/full-download authorization and must be labeled as proxy research.
