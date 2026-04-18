# Options Greeks + Equity Visualization Toolkit Technical Design Outline

**Django · MCP Plugin Architecture · Dual-View Dashboard**

## 1. Purpose and Scope
This document outlines the technical architecture for a dual-view financial visualization toolkit built as a reusable Django app. The toolkit exposes two primary views: an underlying equity chart and a 3D options Greeks surface dashboard. Both views are designed to be driven by a config-injected data source and packaged as a callable MCP tool, making this the first installable visualization plugin in a broader MCP server library.

The core design principle is modularity — the `greeks_viz` Django app should be droppable into any Django project with minimal configuration, and extendable later into a full portfolio management interface without architectural changes.

## 2. Django Project Structure
The toolkit is structured as a standalone Django app (`greeks_viz`) inside a host Django project. This allows it to be installed via pip or copied directly into any existing Django project.

### 2.1 Directory Layout
```text
django_mcp_toolkit/      # Host Django project
    manage.py
    settings.py          # Registers greeks_viz app
    urls.py              # Includes greeks_viz.urls
    wsgi.py
    greeks_viz/          # Reusable Django app
        __init__.py
        apps.py          # AppConfig
        urls.py          # /equity/ and /options/ routes
        views.py         # EquityView, OptionsGreeksView
        services/
            __init__.py
            greeks_calculator.py  # Black-Scholes, py_vollib
            data_router.py        # Config-driven data source loader
            equity_fetcher.py     # OHLCV data retrieval
        templates/
            greeks_viz/
                base.html
                equity_view.html  # Underlying equity window
                options_view.html # 3D Greeks dashboard
        static/
            greeks_viz/
                js/
                    equity_chart.js   # Plotly equity chart logic
                    greeks_grid.js    # 5x2 Greek surface grid logic
                css/
                    dashboard.css
        config/
            data_source.yaml      # Swap data source without code changes
        mcp_tool.py               # Exposes app as callable MCP tool
        tests/
            test_views.py
            test_greeks_calculator.py
```

## 3. The Two Views
The toolkit renders two separate browser windows (or tabs) that can operate independently or be linked by a shared ticker symbol passed via query parameter or session.

### 3.1 View 1 — Underlying Equity
- **Route:** `/greeks-viz/equity/?ticker=AAPL`
- **Purpose:** OHLCV candlestick chart rendered via Plotly.js
- Configurable date range, moving averages, volume bars
- Optional overlay: implied volatility surface pulled from options data
- Live or delayed price feed depending on `data_source.yaml` setting

| Django Component | File | Responsibility |
| --- | --- | --- |
| `EquityView` (CBV) | `views.py` | Renders `equity_view.html`, passes ticker context |
| `equity_fetcher.py` | `services/` | Fetches OHLCV from configured source |
| `data_router.py` | `services/` | Reads `data_source.yaml`, returns adapter |
| `equity_chart.js` | `static/js/` | Plotly candlestick + indicators |

### 3.2 View 2 — Options Greeks 3D Dashboard
- **Route:** `/greeks-viz/options/?ticker=AAPL&expiry=2025-06-20&type=call`
- **Purpose:** 5x2 grid of 3D surface plots — one per three-Greek combination (10 total)
- Each panel renders a Plotly surface: X axis = strike price, Y axis = time to expiry, Z axis = Greek value
- User can toggle individual panels on/off based on their thesis
- Contract selector: ticker, expiry date, call/put toggle
- Optional: stock price overlay projected onto the Greeks surface

| Django Component | File | Responsibility |
| --- | --- | --- |
| `OptionsGreeksView` (CBV) | `views.py` | Renders `options_view.html`, computes Greeks |
| `greeks_calculator.py` | `services/` | Black-Scholes via py_vollib or mibian |
| `data_router.py` | `services/` | Injects options chain data source |
| `greeks_grid.js` | `static/js/` | Renders 5x2 Plotly surface grid |

### 3.3 The Ten Greek Combinations
All ten three-Greek combinations of Delta (Δ), Gamma (Γ), Theta (Θ), Vega (V), and Rho (ρ) are rendered simultaneously. The user hides irrelevant panels rather than pre-selecting.

| Panel | Greeks | Analytical Focus |
| --- | --- | --- |
| 1 | Δ · Γ · Θ | Price sensitivity + time decay |
| 2 | Δ · Γ · V | Direction + volatility curvature |
| 3 | Δ · Γ · ρ | Price sensitivity + rate exposure |
| 4 | Δ · Θ · V | Decay + volatility trade-off |
| 5 | Δ · Θ · ρ | Time + rate interaction |
| 6 | Δ · V · ρ | Full exposure view |
| 7 | Γ · Θ · V | Convexity + decay + vol |
| 8 | Γ · Θ · ρ | Non-delta second-order risk |
| 9 | Γ · V · ρ | Vol curvature + rate sensitivity |
| 10| Θ · V · ρ | No-delta decay and vol view |

## 4. Key Django Components

### 4.1 urls.py — Routing
```python
# greeks_viz/urls.py
from django.urls import path
from .views import EquityView, OptionsGreeksView

urlpatterns = [
    path('equity/', EquityView.as_view(), name='equity_view'),
    path('options/', OptionsGreeksView.as_view(), name='options_view'),
]

# Host project urls.py
# path('greeks-viz/', include('greeks_viz.urls')),
```

### 4.2 views.py — Class-Based Views
```python
# greeks_viz/views.py
from django.views.generic import TemplateView
from .services.greeks_calculator import compute_all_greeks
from .services.data_router import get_data_adapter

class EquityView(TemplateView):
    template_name = 'greeks_viz/equity_view.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ticker = self.request.GET.get('ticker', 'SPY')
        adapter = get_data_adapter()
        ctx['ohlcv'] = adapter.get_equity(ticker)
        ctx['ticker'] = ticker
        return ctx

class OptionsGreeksView(TemplateView):
    template_name = 'greeks_viz/options_view.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ticker = self.request.GET.get('ticker', 'SPY')
        expiry = self.request.GET.get('expiry')
        opt_type = self.request.GET.get('type', 'call')
        
        adapter = get_data_adapter()
        chain = adapter.get_options_chain(ticker, expiry, opt_type)
        
        ctx['greeks_data'] = compute_all_greeks(chain)
        ctx['ticker'] = ticker
        ctx['expiry'] = expiry
        return ctx
```

### 4.3 services/data_router.py — Config-Driven Data Source
This is the central abstraction that makes the toolkit data-source agnostic. Swapping from a CSV to a live exchange API requires only a change in `data_source.yaml`.
```python
# greeks_viz/services/data_router.py
import yaml, importlib

def get_data_adapter():
    with open('greeks_viz/config/data_source.yaml') as f:
        config = yaml.safe_load(f)
    module = importlib.import_module(config['adapter_module'])
    return module.Adapter(config['params'])
```

```yaml
# greeks_viz/config/data_source.yaml
adapter_module: greeks_viz.adapters.csv_adapter  # swap to live_adapter
params:
  file_path: data/options_chain.csv
  # api_key: your_key_here  # used by live adapter
```

### 4.4 services/greeks_calculator.py — Black-Scholes Engine
```python
# greeks_viz/services/greeks_calculator.py
# Recommended library: py_vollib (wraps QuantLib Black-Scholes)
# pip install py_vollib
from py_vollib.black_scholes.greeks import analytical as greeks

COMBINATIONS = [
    ('delta', 'gamma', 'theta'),
    ('delta', 'gamma', 'vega'),
    ('delta', 'gamma', 'rho'),
    ('delta', 'theta', 'vega'),
    ('delta', 'theta', 'rho'),
    ('delta', 'vega', 'rho'),
    ('gamma', 'theta', 'vega'),
    ('gamma', 'theta', 'rho'),
    ('gamma', 'vega', 'rho'),
    ('theta', 'vega', 'rho'),
]

def compute_all_greeks(options_chain):
    results = []
    for combo in COMBINATIONS:
        surface = build_surface(options_chain, combo)
        results.append({'greeks': combo, 'surface': surface})
    return results
```

## 5. MCP Plugin Interface
The toolkit exposes itself as a callable MCP tool via `mcp_tool.py`. This file is the bridge between the Django app and the broader MCP server library. It registers two tools: one for equity data and one for the Greeks dashboard.
```python
# greeks_viz/mcp_tool.py

def register_tools(mcp_server):
    mcp_server.register_tool(
        name='equity_chart',
        description='Renders an OHLCV equity chart for a given ticker',
        handler=equity_chart_handler,
        schema={'ticker': str, 'date_range': str}
    )

    mcp_server.register_tool(
        name='options_greeks_dashboard',
        description='Renders 3D Greeks surface dashboard for an options contract',
        handler=greeks_dashboard_handler,
        schema={'ticker': str, 'expiry': str, 'type': str}
    )
```

## 6. Django Settings Integration
To install `greeks_viz` into any existing Django project, three changes are required in `settings.py`:
```python
# settings.py
INSTALLED_APPS = [
    ... # existing apps
    'greeks_viz',  # add this
]

# Optional: override default data source path
GREEKS_VIZ_CONFIG = {
    'DATA_SOURCE_CONFIG': BASE_DIR / 'greeks_viz/config/data_source.yaml',
    'DEFAULT_TICKER': 'SPY',
    'CHART_LIBRARY': 'plotly',  # plotly | chartjs
}
```

## 7. Frontend Architecture

### 7.1 Equity View
- Template `equity_view.html` renders a single full-width Plotly candlestick chart
- JavaScript receives OHLCV data serialized as JSON from Django context
- `equity_chart.js` handles chart initialization, zoom, date range picker
- Optional: ticker input field at top allows switching symbols without page reload (AJAX call to `/greeks-viz/equity/api/?ticker=X`)

### 7.2 Options Greeks View
- Template `options_view.html` renders the 5x2 panel grid
- Each panel is a Plotly 3D surface (surface type, not scatter) — X: strike, Y: DTE, Z: Greek value
- `greeks_grid.js` iterates over the 10 combinations JSON passed from Django context
- Toggle buttons above the grid show/hide individual panels — no page reload
- Contract selector bar at top: ticker text input, expiry date picker, call/put radio
- Optional stock price plane: a flat horizontal mesh projected onto each surface at current price

## 8. Dependencies
| Package | Purpose |
| --- | --- |
| `django >= 4.2` | Web framework, CBVs, template engine, ORM |
| `py_vollib` | Black-Scholes Greeks calculator (wraps QuantLib) |
| `plotly` | 3D surface plots and candlestick charts (server-side JSON generation) |
| `pandas` | Options chain data manipulation |
| `numpy` | Surface mesh generation for 3D plots |
| `pyyaml` | Parses `data_source.yaml` config |
| `requests` / `httpx` | Live data fetching if using exchange API adapter |
| `pytest-django` | Test suite for views and calculator service |

## 9. Future Extension Points
Because `greeks_viz` is a self-contained Django app, the following extensions can be added as separate apps without modifying the core visualization code:
- `portfolio/` app — save and track option positions, P&L over time
- `alerts/` app — trigger notifications when a Greek crosses a threshold
- `auth/` — Django's built-in auth system, already available once multi-user access is needed
- `strategy_builder/` — combine multiple contracts into spread visualizations (iron condor, straddle, etc.)
- `backtester/` — replay historical Greeks surfaces to evaluate past strategy performance

## 10. Recommended Build Order
1. Scaffold Django project and `greeks_viz` app structure
2. Build `data_router.py` with CSV adapter (no live data dependency yet)
3. Build `greeks_calculator.py` and verify all 10 combinations compute correctly
4. Build `EquityView` + `equity_view.html` with Plotly candlestick
5. Build `OptionsGreeksView` + `options_view.html` with 5x2 surface grid
6. Wire panel toggles and contract selector JS
7. Write `mcp_tool.py` to register both views as MCP tools
8. Swap CSV adapter for live exchange API adapter when ready
