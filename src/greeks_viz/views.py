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
