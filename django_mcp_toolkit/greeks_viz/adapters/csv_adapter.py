import os
import json
from datetime import datetime, timedelta
import random

class Adapter:
    def __init__(self, params):
        self.params = params
        self.file_path = params.get('file_path')

    def get_equity(self, ticker):
        # Return mock OHLCV JSON data suitable for Plotly
        # Format: dict with lists of dates, open, high, low, close, volume
        dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30, 0, -1)]
        open_p = [150 + i + random.uniform(-2, 2) for i in range(30)]
        high_p = [o + random.uniform(0, 5) for o in open_p]
        low_p = [o - random.uniform(0, 5) for o in open_p]
        close_p = [(h + l)/2 for h, l in zip(high_p, low_p)]
        volume = [random.randint(1000000, 5000000) for _ in range(30)]
        
        return json.dumps({
            'dates': dates,
            'open': open_p,
            'high': high_p,
            'low': low_p,
            'close': close_p,
            'volume': volume
        })
        
    def get_options_chain(self, ticker, expiry, opt_type):
        # Return mock data string
        return "mock_chain_data"
