from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Trading Pipeline Dashboard", layout="wide")
st.title("Modular Quant Trading Diagnostics")

artifacts_dir = Path(os.environ.get("TRADING_ARTIFACTS_DIR", "artifacts"))
st.caption(f"Artifacts: {artifacts_dir}")

metrics_path = artifacts_dir / "metrics.json"
if not metrics_path.exists():
    st.warning("No metrics.json found. Run scripts/run_pipeline.py first.")
    st.stop()

with open(metrics_path, "r", encoding="utf-8") as f:
    metrics = json.load(f)

c1, c2, c3 = st.columns(3)
c1.metric("Avg VI", f"{metrics.get('avg_vi', 0):.4f}")
c2.metric("Approval Rate", f"{100.0 * metrics.get('approval_rate', 0):.1f}%")
c3.metric("Post-Exec Sharpe", f"{metrics.get('post_exec', {}).get('sharpe', 0):.3f}")

st.subheader("Performance Summary")
st.json(metrics)

vi_csv = artifacts_dir / "vi_scores.csv"
if vi_csv.exists():
    vi = pd.read_csv(vi_csv)
    if not vi.empty:
        st.subheader("Regime Stability (VI)")
        st.line_chart(vi.set_index("date")["vi"])

orders_csv = artifacts_dir / "executed_orders.csv"
if orders_csv.exists():
    orders = pd.read_csv(orders_csv)
    if not orders.empty:
        daily = orders.groupby("date")["executed_pnl"].sum().sort_index()
        equity = (1.0 + daily).cumprod()
        st.subheader("Executed Equity")
        st.line_chart(equity)

img1 = artifacts_dir / "regime_vi.png"
img2 = artifacts_dir / "equity_curve.png"
if img1.exists():
    st.image(str(img1), caption="Regime VI")
if img2.exists():
    st.image(str(img2), caption="Equity Curve")
