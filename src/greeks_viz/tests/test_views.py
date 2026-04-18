from django.test import TestCase, Client
from django.urls import reverse

class ViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()

    def test_equity_view(self):
        response = self.client.get(reverse('equity_view') + '?ticker=AAPL')
        self.assertEqual(response.status_code, 200)
        self.assertIn('AAPL', response.context['ticker'])
        self.assertIn('ohlcv', response.context)

    def test_options_view(self):
        response = self.client.get(reverse('options_view') + '?ticker=AAPL&expiry=2025-06-20&type=call')
        self.assertEqual(response.status_code, 200)
        self.assertIn('AAPL', response.context['ticker'])
        self.assertEqual('2025-06-20', response.context['expiry'])
        self.assertIn('greeks_data', response.context)
        # Should have 10 combinations
        self.assertEqual(len(response.context['greeks_data']), 10)
