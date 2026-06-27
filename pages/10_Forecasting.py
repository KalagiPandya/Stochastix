"""pages/10_Forecasting.py — Price Forecast Dashboard."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import datetime, timedelta

from pipeline import init_db, fetch_recent_ticks
from services.stream import get_buffer, start_stream
from services.analytics import sma, ema, volatility

st.set_page_config(page_title="Forecasting — Stochastix", page_icon="🔮", layout="wide")

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

# ── Forecast helpers ────────────────────────────────────────────────────────
def linear_forecast(prices, horizon=10):
    if len(prices) < 5: return None, None
    x = np.arange(len(prices))
    slope, intercept = np.polyfit(x, prices, 1)
    future_x = np.arange(len(prices), len(prices) + horizon)
    return slope * future_x + intercept, slope

def exp_smooth_forecast(prices, alpha=0.3, horizon=10):
    if not prices: return None
    s = prices[0]
    for p in prices[1:]: s = alpha * p + (1 - alpha) * s
    return [s] * horizon

def conf_bands(prices, forecast):
    std = np.std(prices[-30:]) if len(prices) >= 30 else np.std(prices)
    return forecast + 1.96 * std, forecast - 1.96 * std

def trend_label(slope, price):
    pct = (slope / price * 100) if price else 0
    if pct > 0.01:  return f"📈 Bullish (+{pct:.3f}%/tick)"
    if pct < -0.01: return f"📉 Bearish ({pct:.3f}%/tick)"
    return "➡️ Sideways"

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔮 Forecast Settings")
    symbol    = st.selectbox("Asset", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    horizon   = st.slider("Horizon (ticks)", 5, 50, 20)
    alpha     = st.slider("Smoothing α", 0.05, 0.95, 0.3, step=0.05)
    lookback  = st.selectbox("Lookback", [50, 100, 200, 300], index=1)
    show_ci   = st.checkbox("Show Confidence Bands", value=True)
    refresh   = st.slider("Refresh (s)", 2, 15, 5)
    st.caption("⚠️ For demonstration only — not financial advice.")

st.title("🔮 Price Forecast Dashboard")
st.caption(f"Linear Regression + Exponential Smoothing · `{symbol}`")

prices_buf = get_buffer(symbol)
ticks_df   = fetch_recent_ticks(symbol, limit=lookback)

if len(prices_buf) < 20 or ticks_df.empty:
    st.info("⏳ Need 20 ticks to forecast."); time.sleep(2); st.rerun()

prices  = prices_buf[-lookback:]
current = prices[-1]
ticks   = ticks_df.sort_values("ts").reset_index(drop=True)

lin_fc, slope    = linear_forecast(prices, horizon)
exp_fc           = exp_smooth_forecast(prices, alpha, horizon)
next_lin         = float(lin_fc[0])  if lin_fc is not None else current
next_exp         = float(exp_fc[0])  if exp_fc is not None else current
next_ensemble    = (next_lin + next_exp) / 2
delta            = next_ensemble - current
delta_pct        = (delta / current * 100) if current else 0

# KPIs
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("💰 Current",         f"${current:,.2f}")
k2.metric("🎯 Next Tick (Ensemble)", f"${next_ensemble:,.2f}",
          f"{delta:+.2f} ({delta_pct:+.2f}%)",
          delta_color="normal" if delta >= 0 else "inverse")
k3.metric("📈 Linear",          f"${next_lin:,.2f}")
k4.metric("🔄 EMA Smooth",      f"${next_exp:,.2f}")
k5.metric("⚡ Volatility σ",    f"{volatility(prices, 20):,.2f}")

st.markdown("---")
col_trend, col_stats = st.columns(2)

with col_trend:
    st.markdown("#### Trend Analysis")
    st.markdown(f"**Direction:** {trend_label(slope, current) if slope is not None else '—'}")
    if slope is not None:
        slope_pct = slope / current * 100
        strength  = min(abs(slope_pct) / 0.05 * 100, 100)
        direction = "Bullish 🐂" if slope > 0 else "Bearish 🐻"
        st.markdown(f"**Slope:** `{slope:+.4f}` ({slope_pct:+.4f}%/tick)")
        st.markdown(f"**Strength:** `{strength:.0f}%` — {direction}")
        st.progress(int(strength))

with col_stats:
    st.markdown("#### Statistical Summary")
    _sma = sma(prices, 20); _ema = ema(prices, 20)
    st.dataframe(pd.DataFrame({
        "Indicator": ["SMA-20","EMA-20","Session High","Session Low","Volatility σ","Price vs SMA"],
        "Value": [
            f"${_sma:,.2f}" if _sma else "—",
            f"${_ema:,.2f}" if _ema else "—",
            f"${max(prices):,.2f}",
            f"${min(prices):,.2f}",
            f"{volatility(prices,20):,.2f}",
            f"{((current-_sma)/_sma*100):+.2f}%" if _sma else "—",
        ],
    }), use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("#### Price History + Forecast")

hist_times = ticks["ts"].tolist()
hist_prices= ticks["price"].tolist()
last_ts    = pd.to_datetime(hist_times[-1]) if hist_times else datetime.now()
future_ts  = [last_ts + timedelta(seconds=2*i) for i in range(1, horizon+1)]

fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                    row_heights=[0.75, 0.25], vertical_spacing=0.05)

fig.add_trace(go.Scatter(x=hist_times, y=hist_prices, name="Price",
                         line=dict(color="#4C9BE8", width=2)), row=1, col=1)

if len(hist_prices) >= 20:
    sma_vals = [sma(hist_prices[:i+1], 20) for i in range(len(hist_prices))]
    fig.add_trace(go.Scatter(x=hist_times, y=sma_vals, name="SMA-20",
                             line=dict(color="#F5A623", width=1.5, dash="dot")), row=1, col=1)

if lin_fc is not None:
    fig.add_trace(go.Scatter(x=future_ts, y=lin_fc.tolist(), name="Linear Forecast",
                             line=dict(color="#7ED321", width=2, dash="dash")), row=1, col=1)
    if show_ci:
        upper, lower = conf_bands(prices, lin_fc)
        fig.add_trace(go.Scatter(
            x=future_ts + future_ts[::-1],
            y=upper.tolist() + lower.tolist()[::-1],
            fill="toself", fillcolor="rgba(126,211,33,0.12)",
            line=dict(color="rgba(0,0,0,0)"), name="95% CI",
        ), row=1, col=1)

if exp_fc is not None:
    fig.add_trace(go.Scatter(x=future_ts, y=exp_fc, name="EMA Smooth",
                             line=dict(color="#B660CD", width=2, dash="dot")), row=1, col=1)

fig.add_vline(x=str(last_ts), line_dash="dash",
              line_color="rgba(255,255,255,0.25)", annotation_text="Now")

if len(hist_prices) > 5:
    vol_vals = [volatility(hist_prices[:i+1], 20) for i in range(len(hist_prices))]
    fig.add_trace(go.Scatter(x=hist_times, y=vol_vals, name="Volatility σ",
                             fill="tozeroy", fillcolor="rgba(232,112,58,0.15)",
                             line=dict(color="#E8703A", width=1)), row=2, col=1)

fig.update_layout(height=500, margin=dict(l=0,r=0,t=10,b=0),
                  legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
                  plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                  font=dict(color="#aaa"), yaxis_title="Price (USDT)", yaxis2_title="σ")
fig.update_xaxes(showgrid=False)
fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
st.plotly_chart(fig, use_container_width=True)

# Forecast table
if lin_fc is not None and exp_fc is not None:
    upper, lower = conf_bands(prices, lin_fc)
    ensemble_arr = (lin_fc + np.array(exp_fc)) / 2
    st.markdown("#### Tick-by-Tick Forecast")
    st.dataframe(pd.DataFrame([{
        "Tick": i+1,
        "Time": future_ts[i].strftime("%H:%M:%S"),
        "Linear ($)": f"${lin_fc[i]:,.2f}",
        "EMA ($)": f"${exp_fc[i]:,.2f}",
        "Ensemble ($)": f"${ensemble_arr[i]:,.2f}",
        "Upper CI": f"${upper[i]:,.2f}",
        "Lower CI": f"${lower[i]:,.2f}",
        "Δ Now": f"{ensemble_arr[i]-current:+.2f}",
    } for i in range(horizon)]), use_container_width=True, hide_index=True)

st.caption("⚠️ Forecasts are for demonstration only — not financial advice.")
time.sleep(refresh)
st.rerun()
