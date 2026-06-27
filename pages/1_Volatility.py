"""pages/1_Volatility.py — Bollinger Bands + rolling volatility."""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import time

from pipeline import fetch_recent_ticks, init_db
from services.stream import get_buffer, start_stream
from services.analytics import volatility, market_stability, rate_of_change, sma

st.set_page_config(page_title="Volatility — Stochastix", page_icon="📉", layout="wide")

st.markdown("""
<style>
[data-testid="metric-container"]{background:#161B22;border:1px solid #21262D;border-radius:10px;padding:16px 20px;}
[data-testid="stSidebar"]{background:#0D1117;border-right:1px solid #21262D;}
hr{border-color:#21262D;}
</style>""", unsafe_allow_html=True)

@st.cache_resource
def ensure():
    init_db(); start_stream(); return True
ensure()

with st.sidebar:
    st.markdown("## 📉 Volatility Settings")
    symbol     = st.selectbox("Asset", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    vol_window = st.slider("Window", 5, 60, 20)
    bb_mult    = st.slider("Bollinger Band σ multiplier", 1.0, 3.0, 2.0, step=0.5)
    refresh    = st.slider("Refresh (s)", 1, 10, 3)

st.title("📉 Volatility Analysis")
st.caption(f"Bollinger Bands ±{bb_mult}σ · Rolling volatility for `{symbol}`")

prices_buf = get_buffer(symbol)
ticks_df   = fetch_recent_ticks(symbol, limit=300)

if len(prices_buf) < 10:
    st.info("⏳ Waiting for data…"); time.sleep(2); st.rerun()

prices      = prices_buf
current_vol = volatility(prices, vol_window)
stability   = market_stability(current_vol)
roc         = rate_of_change(prices, 10)

c1, c2, c3, c4 = st.columns(4)
c1.metric("⚡ Volatility σ", f"{current_vol:,.2f}")
c2.metric("🏥 Stability",    stability)
c3.metric("💰 Price",        f"${prices[-1]:,.2f}")
c4.metric("🔄 ROC (10t)",    f"{roc:.3f}%" if roc else "—")

st.markdown("---")

if not ticks_df.empty:
    ticks_df = ticks_df.sort_values("ts").reset_index(drop=True)
    p = ticks_df["price"].tolist()

    rolling_vol = [volatility(p[:i+1], vol_window) for i in range(len(p))]
    sma_vals    = [sma(p[:i+1], vol_window) for i in range(len(p))]
    upper = [s + bb_mult * v if s else None for s, v in zip(sma_vals, rolling_vol)]
    lower = [s - bb_mult * v if s else None for s, v in zip(sma_vals, rolling_vol)]

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.65, 0.35], vertical_spacing=0.05,
                        subplot_titles=("Price + Bollinger Bands", "Rolling Volatility σ"))

    fig.add_trace(go.Scatter(x=ticks_df["ts"], y=ticks_df["price"],
                             name="Price", line=dict(color="#4C9BE8", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=ticks_df["ts"], y=upper,
                             name=f"+{bb_mult}σ Band",
                             line=dict(color="rgba(245,166,35,0.7)", width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=ticks_df["ts"], y=lower,
                             name=f"-{bb_mult}σ Band",
                             line=dict(color="rgba(245,166,35,0.7)", width=1, dash="dot"),
                             fill="tonexty", fillcolor="rgba(245,166,35,0.06)"), row=1, col=1)
    fig.add_trace(go.Scatter(x=ticks_df["ts"], y=sma_vals,
                             name=f"SMA({vol_window})",
                             line=dict(color="#F5A623", width=1.5, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=ticks_df["ts"], y=rolling_vol,
                             name="Volatility σ", fill="tozeroy",
                             line=dict(color="#E8703A", width=1.5),
                             fillcolor="rgba(232,112,58,0.18)"), row=2, col=1)

    mean_v = float(np.mean([v for v in rolling_vol if v > 0])) if any(v > 0 for v in rolling_vol) else 0
    if mean_v:
        fig.add_hline(y=mean_v, line_dash="dot", line_color="gray",
                      annotation_text="Mean σ", row=2, col=1)

    fig.update_layout(height=560, margin=dict(l=0,r=0,t=30,b=0),
                      legend=dict(orientation="h", y=1.05),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#aaaaaa"))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Volatility Regime Log")
    vol_df = pd.DataFrame({
        "Time":         ticks_df["ts"].tail(20).values,
        "Price":        [f"${v:,.2f}" for v in ticks_df["price"].tail(20).values],
        "Volatility σ": [f"{v:,.2f}" for v in rolling_vol[-20:]],
        "Stability":    [market_stability(v) for v in rolling_vol[-20:]],
    })
    st.dataframe(vol_df[::-1], use_container_width=True, hide_index=True)

time.sleep(refresh)
st.rerun()
