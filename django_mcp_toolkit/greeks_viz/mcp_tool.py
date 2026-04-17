def equity_chart_handler(params):
    return f"http://localhost:8000/greeks-viz/equity/?ticker={params.get('ticker')}"

def greeks_dashboard_handler(params):
    ticker = params.get('ticker')
    expiry = params.get('expiry', '')
    opt_type = params.get('type', 'call')
    return f"http://localhost:8000/greeks-viz/options/?ticker={ticker}&expiry={expiry}&type={opt_type}"

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
