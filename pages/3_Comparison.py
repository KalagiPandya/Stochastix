"""pages/3_Comparison.py — Multi-asset comparison + OHLC candlestick."""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import time

from pipeline import fetch_recent_ticks, fetch_candles, init_db
from services.stream import get_buffer, start_stream
from services.analytics import sma, ema, volatility, z_score

st.set_page_config(page_title="Comparison — Stochastix", page_icon="📊", layout="wide")

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

COLORS = {"BTCUSDT": "#F7931A", "ETHUSDT": "#627EEA", "SOLUSDT": "#9945FF"}

with st.sidebar:
    st.markdown("## 📊 Comparison Settings")
    assets     = st.multiselect("Assets", ["BTCUSDT", "ETHUSDT", "SOLUSDT"], default=["BTCUSDT", "ETHUSDT"])
    chart_type = st.radio("View", ["Normalised Price", "Candlestick", "Metrics Table"])
    refresh    = st.slider("Refresh (s)", 1, 10, 3)

st.title("📊 Multi-Asset Comparison")
st.caption("Normalised performance · OHLC candlestick · Metrics heatmap")

if not assets:
    st.warning("Select at least one asset in the sidebar."); st.stop()

all_data = {sym: get_buffer(sym) for sym in assets if get_buffer(sym)}

if not all_data:
    st.info("⏳ Waiting for data…"); time.sleep(2); st.rerun()

# KPI row
cols = st.columns(len(all_data))
for i, (sym, prices) in enumerate(all_data.items()):
    with cols[i]:
        p    = prices[-1]
        prev = prices[-2] if len(prices) > 1 else p
        vol  = volatility(prices, 20)
        st.metric(sym, f"${p:,.2f}", f"{p-prev:+.2f}")
        st.caption(f"σ = {vol:,.2f}")

st.markdown("---")

if chart_type == "Normalised Price":
    fig = go.Figure()
    for sym, prices in all_data.items():
        df = fetch_recent_ticks(sym, limit=300)
        if df.empty: continue
        df = df.sort_values("ts").reset_index(drop=True)
        base = df["price"].iloc[0]
        fig.add_trace(go.Scatter(x=df["ts"], y=(df["price"]/base - 1)*100,
                                 name=sym[:3], line=dict(color=COLORS.get(sym,"#fff"), width=2)))
    fig.add_hline(y=0, line_color="rgba(128,128,128,0.4)", line_dash="dot")
    fig.update_layout(title="Normalised Performance (% from session start)",
                      height=450, margin=dict(l=0,r=0,t=40,b=0),
                      yaxis_title="% Change",
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#aaaaaa"), legend=dict(orientation="h", y=1.08))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
    st.plotly_chart(fig, use_container_width=True)

elif chart_type == "Candlestick":
    sym = assets[0]
    df  = fetch_candles(sym, limit=100)
    if df.empty:
        st.info("⏳ Building candles — check back in ~1 minute.")
    else:
        df = df.sort_values("candle_ts").reset_index(drop=True)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            row_heights=[0.75, 0.25], vertical_spacing=0.04,
                            subplot_titles=(f"{sym} — 1 Min OHLC", "Volume"))
        fig.add_trace(go.Candlestick(
            x=df["candle_ts"], open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="OHLC",
            increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        ), row=1, col=1)
        bar_colors = ["#26a69a" if c >= o else "#ef5350"
                      for c, o in zip(df["close"], df["open"])]
        fig.add_trace(go.Bar(x=df["candle_ts"], y=df["volume"],
                             marker_color=bar_colors, opacity=0.6, name="Volume"), row=2, col=1)
        fig.update_layout(height=520, margin=dict(l=0,r=0,t=30,b=0),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#aaaaaa"), xaxis_rangeslider_visible=False)
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
        st.plotly_chart(fig, use_container_width=True)

else:  # Metrics Table
    rows = []
    for sym, prices in all_data.items():
        _s = sma(prices, 20); _e = ema(prices, 20)
        _v = volatility(prices, 20); _z = z_score(prices[-1], prices, 30)
        rows.append({
            "Asset": sym[:3], "Price": f"${prices[-1]:,.2f}",
            "SMA(20)": f"${_s:,.2f}" if _s else "—",
            "EMA(20)": f"${_e:,.2f}" if _e else "—",
            "Volatility σ": f"{_v:,.2f}",
            "Z-score": f"{_z:.3f}" if _z else "—",
            "Anomaly": "🚨 Yes" if _z and abs(_z) > 2.5 else "✅ No",
            "High": f"${max(prices):,.2f}", "Low": f"${min(prices):,.2f}",
            "Ticks": len(prices),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

time.sleep(refresh)
st.rerun()
