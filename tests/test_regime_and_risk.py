from __future__ import annotations

import numpy as np
import pandas as pd

from trading.regime import variation_of_information
from trading.risk import summarize_performance


def test_variation_of_information_zero_for_identical_labels() -> None:
    x = np.array([0, 0, 1, 1, 2, 2])
    y = np.array([0, 0, 1, 1, 2, 2])
    assert variation_of_information(x, y) < 1e-9


def test_summarize_performance_shapes() -> None:
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=6, freq="D"),
            "realized_pnl": [0.01, -0.01, 0.005, 0.004, -0.002, 0.003],
        }
    )
    out = summarize_performance(df)
    assert set(out) == {"mean_daily_return", "vol_daily_return", "sharpe", "cum_return"}
