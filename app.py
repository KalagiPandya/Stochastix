"""
app.py — Stochastix PRO | Home Dashboard
Real-time BTC/ETH/SOL analytics with live WebSocket streaming.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time

from pipeline import init_db, fetch_recent_ticks, DB_BACKEND
from services.stream import start_stream, get_buffer
from services.analytics import sma, ema, volatility, z_score, rate_of_change, market_stability

st.set_page_config(
    page_title="Stochastix PRO",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Metric cards */
    [data-testid="metric-container"] {
        background: #161B22;
        border: 1px solid #21262D;
        border-radius: 10px;
        padding: 16px 20px;
    }
    [data-testid="metric-container"]:hover {
        border-color: #4C9BE8;
        transition: border-color 0.2s;
    }
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #0D1117;
        border-right: 1px solid #21262D;
    }
    /* Headers */
    h1 { color: #E6EDF3; font-weight: 700; }
    h2, h3, h4 { color: #C9D1D9; }
    /* Tabs */
    [data-testid="stTab"] { font-weight: 600; }
    /* Dataframe */
    [data-testid="stDataFrame"] { border: 1px solid #21262D; border-radius: 8px; }
    /* Divider */
    hr { border-color: #21262D; margin: 0.5rem 0; }
</style>
""", unsafe_allow_html=True)

# ── Bootstrap ─────────────────────────────────────────────────────────────────
@st.cache_resource
def bootstrap():
    init_db()
    start_stream()
    return True

bootstrap()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    symbol = st.selectbox("Asset", ["BTCUSDT", "ETHUSDT", "SOLUSDT"], index=0)
    sma_window = st.slider("SMA Window", 5, 60, 20)
    ema_window = st.slider("EMA Window", 5, 60, 20)
    anomaly_thresh = st.slider("Anomaly Z-threshold", 1.5, 4.0, 2.5, step=0.1)
    refresh_rate = st.slider("Refresh (seconds)", 1, 10, 2)
    st.markdown("---")
    st.caption(f"🗄 Backend: **{DB_BACKEND.upper()}**")
    st.caption("📡 Binance WebSocket")
    user = st.session_state.get("user")
    if user:
        st.markdown("---")
        st.caption(f"🔐 **{user['username']}** ({user['role']})")

# ── Header ────────────────────────────────────────────────────────────────────
col_title, col_badge = st.columns([4, 1])
with col_title:
    st.title("📈 Stochastix PRO")
    st.caption(f"Live `{symbol}` · Auto-refresh every {refresh_rate}s")
with col_badge:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"**`LIVE`**")

# ── Fetch data ────────────────────────────────────────────────────────────────
prices_buf = get_buffer(symbol)
ticks_df = fetch_recent_ticks(symbol, limit=300)

if len(prices_buf) < 5:
    st.info("⏳ Connecting to Binance... prices will appear in a few seconds.")
    time.sleep(2)
    st.rerun()

prices = prices_buf
current_price = prices[-1]
prev_price = prices[-2] if len(prices) > 1 else current_price
price_delta = current_price - prev_price
price_delta_pct = (price_delta / prev_price * 100) if prev_price else 0

_sma  = sma(prices, sma_window)
_ema  = ema(prices, ema_window)
_vol  = volatility(prices, sma_window)
_z    = z_score(current_price, prices, 30)
_roc  = rate_of_change(prices, 10)
_stab = market_stability(_vol)

# ── KPI Row ───────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric(f"💰 {symbol[:3]} Price", f"${current_price:,.2f}", f"{price_delta:+.2f} ({price_delta_pct:+.2f}%)")
c2.metric("📊 SMA", f"${_sma:,.2f}" if _sma else "—")
c3.metric("📈 EMA", f"${_ema:,.2f}" if _ema else "—")
c4.metric("⚡ Volatility σ", f"{_vol:,.2f}")
c5.metric("🔄 ROC (10t)", f"{_roc:.3f}%" if _roc else "—")
c6.metric("🏥 Stability", _stab)

# ── Anomaly alert ─────────────────────────────────────────────────────────────
if _z is not None and abs(_z) > anomaly_thresh:
    direction = "SPIKE ▲" if _z > 0 else "DROP ▼"
    st.error(f"🚨 **Anomaly Detected** — {direction}  |  Z = `{_z:.2f}`  |  Price = `${current_price:,.2f}`")

st.markdown("---")

# ── Main chart ────────────────────────────────────────────────────────────────
if not ticks_df.empty:
    ticks_df = ticks_df.sort_values("ts").reset_index(drop=True)
    p_list = ticks_df["price"].tolist()

    sma_line = [sma(p_list[:i+1], sma_window) for i in range(len(p_list))]
    ema_line = [ema(p_list[:i+1], ema_window) for i in range(len(p_list))]
    vol_vals  = [volatility(p_list[:i+1], sma_window) for i in range(len(p_list))]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.04,
    )

    fig.add_trace(go.Scatter(
        x=ticks_df["ts"], y=ticks_df["price"],
        name="Price", line=dict(color="#4C9BE8", width=2), mode="lines",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=ticks_df["ts"], y=sma_line,
        name=f"SMA({sma_window})", line=dict(color="#F5A623", width=1.5, dash="dot"),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=ticks_df["ts"], y=ema_line,
        name=f"EMA({ema_window})", line=dict(color="#7ED321", width=1.5, dash="dash"),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=ticks_df["ts"], y=vol_vals,
        name="Volatility σ", fill="tozeroy",
        line=dict(color="#E8703A", width=1),
        fillcolor="rgba(232,112,58,0.15)",
    ), row=2, col=1)

    fig.update_layout(
        height=520, margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#aaaaaa"),
        yaxis_title="Price (USDT)", yaxis2_title="σ",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
    st.plotly_chart(fig, use_container_width=True)

# ── Session summary ───────────────────────────────────────────────────────────
st.markdown("---")
col_a, col_b = st.columns(2)
with col_a:
    st.markdown("#### Session Stats")
    st.markdown(f"**Stability:** {_stab}")
    st.markdown(f"**Z-score:** `{_z:.3f}`" if _z else "**Z-score:** `—`")
    st.markdown(f"**Ticks in buffer:** `{len(prices)}`")
with col_b:
    st.markdown("#### Price Range")
    if prices:
        hi, lo = max(prices), min(prices)
        st.markdown(f"**High:** `${hi:,.2f}`")
        st.markdown(f"**Low:** `${lo:,.2f}`")
        st.markdown(f"**Range:** `${hi - lo:,.2f}`")

time.sleep(refresh_rate)
st.rerun()
