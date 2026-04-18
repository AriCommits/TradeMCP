import unittest
from greeks_viz.mcp_tool import equity_chart_handler, greeks_dashboard_handler, register_tools

class MockMCPServer:
    def __init__(self):
        self.tools = {}
        
    def register_tool(self, name, description, handler, schema):
        self.tools[name] = handler

class MCPToolTestCase(unittest.TestCase):
    def test_equity_chart_handler(self):
        url = equity_chart_handler({'ticker': 'AAPL'})
        self.assertEqual(url, 'http://localhost:8000/greeks-viz/equity/?ticker=AAPL')

    def test_greeks_dashboard_handler(self):
        url = greeks_dashboard_handler({'ticker': 'AAPL', 'expiry': '2025-06-20', 'type': 'call'})
        self.assertEqual(url, 'http://localhost:8000/greeks-viz/options/?ticker=AAPL&expiry=2025-06-20&type=call')
        
    def test_register_tools(self):
        server = MockMCPServer()
        register_tools(server)
        self.assertIn('equity_chart', server.tools)
        self.assertIn('options_greeks_dashboard', server.tools)
