# Rust Kernel Assessment

**Status:** Sprint 1 audit
**Audited source:** `C:\Users\arian\Github\Agent_00Quant\TradeMCP\backend\rust_exec_engine`
**Integration decision:** Do not copy the subtree source automatically. Retain Python as the orchestration layer and promote Rust only behind a reviewed, versioned numerical interface.

## Executive assessment

The subtree contains tested implementations of Black-Scholes-Merton pricing and Greeks, a Cox-Ross-Rubinstein binomial tree, common technical indicators, and a next-bar equity backtester. These are promising numerical kernels, but none is ready to drive options trade setup.

The compiled program currently exposes only an execution-shortfall filter over JSON standard input/output. The pricing, indicator, and backtest modules are private modules of the binary: they have no stable library API, Python binding, MCP tool, schema version, or serialization contract. The equity backtester does not model option quotes, spreads, contract multipliers, exercise, assignment, settlement, margin, dividends, or multi-leg positions.

The most important pricing blocker is a hard minimum time to expiry of one calendar day. A Friday-to-Monday experiment may happen to exceed that floor, but same-day and sub-day values cannot be represented accurately. This behavior must not be used for 0DTE decisions.

## Verified baseline

`cargo test --locked` passed all **31 tests** on 2026-07-12 with `CARGO_TARGET_DIR` located under the system temporary directory. The suite covers basic pricing identities, indicator examples, equity backtest behavior, and two execution-filter decisions. Eight compiler warnings remain, primarily unused fields/functions.

Passing these tests establishes consistency with the subtree's current assumptions; it does not establish market-data correctness, production numerical robustness, or suitability for live trading.

## Pricing kernel

### Black-Scholes-Merton

Inputs and observed conventions:

| Input | Current meaning | Unit |
|---|---|---|
| `s` | Underlying spot price | Currency per share |
| `k` | Strike price | Currency per share |
| `t` | Time to expiry | Calendar years |
| `r` | Continuously compounded risk-free rate | Annual decimal |
| `sigma` | Volatility | Annualized decimal |
| `q` | Continuous dividend yield | Annual decimal |
| `is_call` | Call when true, put when false | Boolean |

Outputs are per underlying share, before applying an option contract multiplier:

| Output | Current convention |
|---|---|
| `price` | Currency per share |
| `delta` | Price change per one currency-unit spot move |
| `gamma` | Delta change per one currency-unit spot move |
| `theta` | Price change per one calendar **year**, not per day |
| `vega` | Price change per `1.0` absolute volatility, not per 1 volatility point |
| `rho` | Price change per `1.0` absolute rate, not per 1 rate point |

The implementation uses the European Black-Scholes-Merton equations with a continuous dividend yield. It is not a quote model: the market price remains the source for implied volatility, and no implied-volatility solver exists.

Current validation and clamps:

- Spot and strike must be positive.
- Every `t < 1/365`, including zero and negative values, is silently replaced by `1/365`.
- Every `sigma < 1e-10`, including zero and negative values, is silently replaced by `1e-10`.
- NaN/infinity, implausible rates or yields, timestamp ordering, and unit mismatches are not rejected.

The silent time clamp materially overstates remaining time for 0DTE options. The silent volatility clamp also conflates a deterministic boundary case with a small-volatility approximation. A production interface should validate finite inputs, compute time from explicit UTC decision and expiration timestamps, reject negative time, and either implement well-defined expiry/zero-volatility limits or return typed errors.

### Cox-Ross-Rubinstein binomial tree

The tree uses the same units and the same one-day/time and volatility clamps. It supports European or American exercise and a continuous dividend yield. American exercise is evaluated only at tree nodes.

Additional limitations:

- `steps` is not validated as positive.
- The risk-neutral probability is not checked to be finite or within `[0, 1]`.
- No convergence policy or error estimate chooses an adequate step count.
- Very small volatility can make `u - d` numerically unstable.
- There are no discrete cash dividends, ex-dividend timestamps, term structures, borrow costs, or trading calendars.
- The function returns price only; Greeks and exercise-boundary diagnostics are absent.

The binomial function is a useful American-option baseline after validation and discrete-dividend design, but it is not yet a lifecycle or assignment model.

### Portable fixtures

Language-neutral fixtures live in `tests/fixtures/options_pricing/`:

- `black_scholes_v1.json` fixes units, Greek scaling, ordinary cases, and the legacy one-day/zero-volatility clamp behavior.
- `binomial_v1.json` fixes representative European and American prices at explicit step counts.

`tests/test_options_pricing_fixtures.py` independently evaluates the documented equations, put-call parity, and the American-put lower bound. Clamp cases are compatibility fixtures, not endorsements: a corrected sub-day implementation should introduce a new fixture/model version instead of silently changing version 1.

## Indicator kernel

Implemented functions are SMA, EMA, Wilder-style RSI, Wilder-style ATR, OBV, MACD, Bollinger bands, stochastic oscillator, ADX, and cumulative typical-price VWAP.

Important conventions and limitations:

- EMA is seeded with the first full-window SMA.
- RSI and ATR use Wilder smoothing after a simple-average seed.
- Bollinger variance divides by `period` (population variance), not `period - 1`.
- VWAP is cumulative over the entire supplied slice and has no session reset.
- Missing warm-up outputs are `None`; missing observations inside input arrays are not modeled.
- Input arrays are assumed to have matching lengths and valid high/low/close relationships. Several functions can panic on mismatched lengths.
- Zero periods are not safely handled by every function; stochastic and Bollinger loop bounds can underflow.
- Non-finite and negative volume/price inputs are not rejected.
- The initial ADX calculation can divide by zero before its later zero-range guards.
- There are no timestamps, session calendars, corporate-action adjustments, or point-in-time provenance.

These functions may eventually serve feature generation, but technical indicators are not required for the strategy-neutral options core. Any adoption should add typed input validation and parity fixtures against the Python feature definitions rather than creating a second, divergent feature pipeline.

## Equity backtest kernel

The backtester applies the last signal for a bar at the next bar's open. It supports long, short, or flat directions, proportional entry/exit commission, proportional adverse slippage, fractional shares, full-capital allocation, mark-to-market equity, and summary metrics.

Material assumptions and gaps:

- Signal confidence is stored but unused.
- Signals on the last bar are ignored; open positions are not forcibly closed at the end.
- Trade statistics include only closed trades while total return includes the marked open position.
- The Sharpe calculation always applies `sqrt(252)`, regardless of bar frequency.
- Cash yield, borrow fees, dividends, locate constraints, taxes, lot sizes, partial fills, bid/ask quotes, and market sessions are absent.
- Input values and configurations are not validated for finite/positive values.
- It is an all-in single-asset equity simulator, not a portfolio or options simulator.

Do not extend this function by adding option-specific conditionals. The future option simulator should consume canonical legs/positions and explicitly model quote-side fills, multipliers, expiration, exercise/assignment, settlement, margin/collateral, dividends, and multi-leg accounting.

## Execution binary and security difference

The subtree `execution_client.py` executes any configured path that exists and is a file. The base TradeMCP copy first resolves the path and applies an executable-path check. That base check must be preserved during any subtree integration.

The base check is a useful defense but should be hardened before live use:

- String-prefix containment can confuse a repository path with a sibling that shares its prefix; use `Path.relative_to`/`is_relative_to` semantics.
- Allowing any external file merely because its basename is `rust_exec_engine` or `rust_exec_engine.exe` still permits an untrusted same-named binary.
- Add an explicit configured allowlist, file ownership/permission checks where available, an expected build artifact location, and optionally a release hash/signature.
- Add subprocess timeout, stdout/stderr size limits, response schema validation, and fail-closed behavior for live modes.

The current Python and Rust fallback shortfall formulas also differ for BUY orders: Rust applies a `1.05` side multiplier while Python does not. Their rejection `reason` values differ as well. This is a parity issue that must be fixed before treating the Rust binary as interchangeable with the fallback.

## Unsupported options cases

Neither the subtree kernels nor the binary currently support:

- Historical or live option-chain ingestion and NBBO provenance
- Implied-volatility inversion or volatility surfaces
- Discrete dividends and early-exercise risk around ex-dividend dates
- Sub-day/0DTE time measurement
- Interest-rate, dividend, volatility, or borrow term structures
- Bid/ask fill models, quote staleness, crossed markets, or liquidity limits
- Contract multipliers, OCC symbology, adjustments, or corporate actions
- Expiration calendars, AM/PM settlement, cash versus physical settlement
- Exercise, assignment, pin risk, or broker cutoffs
- Margin, cash collateral, portfolio buying power, or liquidation
- Multi-leg atomicity and partial fills
- Weekend gap distributions or event calendars
- Strategy-neutral forecast schemas or trade-plan safety/provenance records

## Safe integration route

1. **Freeze contracts first.** Use the canonical Python domain and time/unit contracts from Sprint 1 as the authority. Rust should implement those contracts, not define competing ones.
2. **Keep fixtures language-neutral.** Require Python and Rust to read the same versioned JSON cases. Add corrected sub-day, expiry-boundary, discrete-dividend, invalid-input, and randomized property tests before enabling 0DTE work.
3. **Create a Rust library boundary.** In the subtree development line, separate pure kernels into a library crate with typed errors and no process execution. Review the exact diff before porting or merging it into TradeMCP.
4. **Expose a versioned batch API.** Start with a bounded JSON-lines subprocess interface for batch pricing. Include `schema_version`, `request_id`, explicit units, model identifier/version, and structured errors. Keep the executable at an allowlisted repository build path.
5. **Validate at the Python boundary.** Python owns timestamps, calendars, market-data provenance, orchestration, and strategy simulation. It must validate finite ranges, map expiration timestamps to positive year fractions, enforce timeouts, and reject malformed/partial responses.
6. **Require parity and fallbacks.** Compare Rust with an independent Python reference over fixtures and randomized domains. A failure must disable the Rust acceleration path, surface diagnostics, and never silently change a trade plan.
7. **Optimize only after profiling.** Use subprocess batching first. Consider PyO3/maturin only if serialization/process overhead is material; this research platform is not latency-sensitive.
8. **Keep live execution separate.** Pricing acceleration must not grant order-placement authority. MCP tools should return research or paper-trade plans until broker-specific approvals and safety gates are implemented.

## Adoption recommendation

| Module | Recommendation | Gate |
|---|---|---|
| Black-Scholes/Greeks | Adopt after correction and parity work | Typed validation, real sub-day time, IV solver, v2 fixtures |
| Binomial tree | Adopt as a reference American pricer | Step/probability validation, discrete dividends, convergence tests |
| Indicators | Selectively reuse only if parity is valuable | Safe dimensions/periods, session semantics, feature parity tests |
| Equity backtester | Keep as a separate prototype | Do not use as the option lifecycle engine |
| Execution-shortfall binary | Retain only as an optional experimental filter | Harden executable trust and restore Python/Rust parity |

No audited Rust source was copied into the base repository as part of this sprint.
