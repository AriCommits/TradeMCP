from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

try:
    from arch import arch_model  # type: ignore
except Exception:  # pragma: no cover
    arch_model = None


def _ewma_forecast(returns: np.ndarray, lam: float, horizon: int) -> float:
    if len(returns) == 0:
        return np.nan
    var = np.var(returns)
    for r in returns:
        var = lam * var + (1 - lam) * (r**2)
    return float(np.sqrt(var * horizon))


def _garch_forecast(returns: np.ndarray, horizon: int, lam: float) -> float:
    clean = returns[np.isfinite(returns)]
    if len(clean) < 30 or arch_model is None:
        return _ewma_forecast(clean, lam=lam, horizon=horizon)

    scaled = clean * 100.0
    model = arch_model(scaled, mean="Zero", vol="GARCH", p=1, q=1, dist="normal")
    fitted = model.fit(disp="off")
    forecast = fitted.forecast(horizon=horizon)
    v = forecast.variance.values[-1].mean()
    return float(np.sqrt(v) / 100.0)


def forecast_cluster_volatility(
    df: pd.DataFrame,
    assignments: pd.DataFrame,
    lookback_days: int,
    horizon_days: int,
    model: str,
    ewma_lambda: float,
) -> pd.DataFrame:
    if assignments.empty:
        return pd.DataFrame(columns=["date", "symbol", "vol_forecast"])

    rows = []
    model = model.lower()

    for d, day_assign in assignments.groupby("date"):
        date = pd.Timestamp(d)
        window = df[(df["date"] <= date) & (df["date"] >= date - pd.Timedelta(days=lookback_days))]

        for regime, rg_assign in day_assign.groupby("regime"):
            symbols = rg_assign["symbol"].tolist()
            sub = window[window["symbol"].isin(symbols)]

            pivot = sub.pivot(index="date", columns="symbol", values="log_return").dropna(axis=1, how="all")
            pivot = pivot.fillna(0.0)
            if pivot.empty:
                continue

            if pivot.shape[1] == 1:
                factor = pivot.iloc[:, 0].values
            else:
                factor = PCA(n_components=1).fit_transform(pivot.values).reshape(-1)

            if model == "garch":
                vol = _garch_forecast(factor, horizon=horizon_days, lam=ewma_lambda)
            else:
                vol = _ewma_forecast(factor, lam=ewma_lambda, horizon=horizon_days)

            for symbol in symbols:
                rows.append(
                    {
                        "date": date,
                        "symbol": symbol,
                        "regime": int(regime),
                        "vol_forecast": float(vol),
                    }
                )

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["date", "symbol", "vol_forecast", "regime"])
    return out
