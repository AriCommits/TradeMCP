from __future__ import annotations

from dataclasses import dataclass
import warnings

import numpy as np
import pandas as pd
from sklearn.decomposition import FastICA, PCA
from sklearn.metrics import mutual_info_score

try:
    import umap  # type: ignore
except Exception:  # pragma: no cover
    umap = None

try:
    import hdbscan  # type: ignore
except Exception:  # pragma: no cover
    hdbscan = None


@dataclass
class RegimeResult:
    assignments: pd.DataFrame
    vi_scores: pd.DataFrame


def _entropy(labels: np.ndarray) -> float:
    labels = np.asarray(labels)
    if labels.size == 0:
        return 0.0
    _, counts = np.unique(labels, return_counts=True)
    probs = counts / counts.sum()
    return float(-(probs * np.log(probs + 1e-12)).sum())


def variation_of_information(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) != len(y):
        raise ValueError("Inputs must have the same length")
    hx = _entropy(x)
    hy = _entropy(y)
    mi = mutual_info_score(x, y)
    return float(hx + hy - 2.0 * mi)


def _fit_cluster(embedding: np.ndarray, min_cluster_size: int) -> np.ndarray:
    if hdbscan is not None:
        model = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size)
        return model.fit_predict(embedding)

    from sklearn.cluster import DBSCAN

    model = DBSCAN(eps=0.8, min_samples=max(2, min_cluster_size // 2))
    return model.fit_predict(embedding)


def _embed(features: np.ndarray, pca_components: int, ica_components: int, umap_components: int) -> np.ndarray:
    pca = PCA(n_components=min(pca_components, features.shape[1]))
    ica = FastICA(
        n_components=min(ica_components, features.shape[1]),
        random_state=42,
        whiten="unit-variance",
        max_iter=600,
        tol=0.01,
    )

    pca_z = pca.fit_transform(features)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ica_z = ica.fit_transform(features)

    concat = np.hstack([pca_z, ica_z])
    if umap is None or features.shape[0] < 20:
        return concat

    reducer = umap.UMAP(
        n_components=umap_components,
        random_state=42,
        n_neighbors=min(15, features.shape[0] - 1),
    )
    return reducer.fit_transform(concat)


def discover_regimes(
    df: pd.DataFrame,
    rebalance_days: int,
    lookback_days: int,
    pca_components: int,
    ica_components: int,
    umap_components: int,
    min_cluster_size: int,
) -> RegimeResult:
    dates = sorted(df["date"].unique())
    rebalance_dates = dates[::rebalance_days]

    assignments = []
    vi_rows = []

    prev_map: dict[str, int] | None = None
    prev_date = None

    for d in rebalance_dates:
        window_start = pd.Timestamp(d) - pd.Timedelta(days=lookback_days)
        window = df[(df["date"] <= d) & (df["date"] >= window_start)]

        if window.empty:
            continue

        symbol_stats = (
            window.groupby("symbol")
            .agg(
                mean_ret=("log_return_scaled", "mean"),
                std_ret=("log_return_scaled", "std"),
                mean_vol=("realized_vol_scaled", "mean"),
                mean_dv=("dollar_volume_scaled", "mean"),
            )
            .dropna()
        )

        if len(symbol_stats) < max(3, min_cluster_size):
            continue

        embedding = _embed(
            symbol_stats.values,
            pca_components=pca_components,
            ica_components=ica_components,
            umap_components=umap_components,
        )
        labels = _fit_cluster(embedding, min_cluster_size=min_cluster_size)

        current_map = dict(zip(symbol_stats.index.tolist(), labels.tolist(), strict=True))

        for symbol, regime in current_map.items():
            assignments.append({"date": pd.Timestamp(d), "symbol": symbol, "regime": int(regime)})

        if prev_map is not None and prev_date is not None:
            overlap = sorted(set(prev_map) & set(current_map))
            if overlap:
                prev_labels = np.array([prev_map[s] for s in overlap])
                curr_labels = np.array([current_map[s] for s in overlap])
                vi = variation_of_information(prev_labels, curr_labels)
                vi_rows.append(
                    {
                        "date": pd.Timestamp(d),
                        "prev_date": pd.Timestamp(prev_date),
                        "n_overlap": len(overlap),
                        "vi": float(vi),
                    }
                )

        prev_map = current_map
        prev_date = d

    assignments_df = pd.DataFrame(assignments)
    vi_df = pd.DataFrame(vi_rows)
    return RegimeResult(assignments=assignments_df, vi_scores=vi_df)
