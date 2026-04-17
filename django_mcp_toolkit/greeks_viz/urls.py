from django.urls import path
from .views import EquityView, OptionsGreeksView

urlpatterns = [
    path('equity/', EquityView.as_view(), name='equity_view'),
    path('options/', OptionsGreeksView.as_view(), name='options_view'),
]
