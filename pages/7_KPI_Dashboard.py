"""pages/7_KPI_Dashboard.py — Business KPI Dashboard."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import time

from pipeline import init_db, fetch_recent_ticks, fetch_analytics, count_anomalies, fetch_latest_price
from services.stream import get_buffer, start_stream

st.set_page_config(page_title="KPI Dashboard — Stochastix", page_icon="📊", layout="wide")

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
    st.markdown("## 📊 KPI Settings")
    symbol        = st.selectbox("Asset", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    lookback      = st.selectbox("Lookback", [50, 100, 200, 300], index=1)
    anomaly_window= st.slider("Anomaly Window (min)", 10, 120, 60)
    refresh       = st.slider("Refresh (s)", 2, 15, 5)

st.title("📊 Business KPI Dashboard")
st.caption(f"Executive metrics · `{symbol}`")

ticks_df      = fetch_recent_ticks(symbol, limit=lookback)
analytics_df  = fetch_analytics(symbol, limit=lookback)
current_price = fetch_latest_price(symbol)
anomaly_count = count_anomalies(symbol, minutes=anomaly_window)

if ticks_df.empty or current_price is None:
    st.info("⏳ Collecting data…"); time.sleep(2); st.rerun()

prices        = ticks_df["price"].tolist()
total_records = len(ticks_df)
avg_price     = sum(prices) / len(prices)
high_price    = max(prices)
low_price     = min(prices)
price_range   = high_price - low_price
total_volume  = ticks_df["volume"].sum() if "volume" in ticks_df.columns else 0
anomaly_rate  = (anomaly_count / total_records * 100) if total_records else 0

# KPI cards
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("📦 Total Records", f"{total_records:,}", "Live")
k2.metric("💰 Avg Price",     f"${avg_price:,.2f}",
          f"{((current_price-avg_price)/avg_price*100):+.2f}% vs avg" if avg_price else None)
k3.metric("📈 Session High",  f"${high_price:,.2f}")
k4.metric("📉 Session Low",   f"${low_price:,.2f}")
k5.metric("🚨 Anomalies",     str(anomaly_count),
          f"{anomaly_rate:.1f}% rate",
          delta_color="inverse" if anomaly_count > 5 else "normal")
k6.metric("📊 Volume",        f"{total_volume:,.0f}" if total_volume > 0 else "N/A")

st.markdown("---")

col_chart, col_gauge = st.columns([2, 1])

with col_chart:
    st.markdown("#### Price Trend")
    ts = ticks_df.sort_values("ts")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ts["ts"], y=ts["price"],
                             fill="tozeroy", fillcolor="rgba(76,155,232,0.1)",
                             line=dict(color="#4C9BE8", width=2), name="Price"))
    fig.add_hline(y=avg_price, line_dash="dash", line_color="#F5A623",
                  annotation_text=f"Avg ${avg_price:,.0f}")
    fig.update_layout(height=260, margin=dict(l=0,r=0,t=10,b=0),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#aaaaaa"), showlegend=False, yaxis_title="Price (USDT)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
    st.plotly_chart(fig, use_container_width=True)

with col_gauge:
    st.markdown("#### Market Health")
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number",
        value=anomaly_rate,
        number={"suffix": "%", "font": {"size": 28, "color": "#fff"}},
        title={"text": "Anomaly Rate", "font": {"color": "#aaa", "size": 13}},
        gauge={
            "axis": {"range": [0, 20], "tickcolor": "#aaa"},
            "bar":  {"color": "#4C9BE8"},
            "steps": [
                {"range": [0, 5],  "color": "rgba(126,211,33,0.3)"},
                {"range": [5, 10], "color": "rgba(245,166,35,0.3)"},
                {"range": [10,20], "color": "rgba(232,112,58,0.3)"},
            ],
            "threshold": {"line": {"color": "#E8703A", "width": 3},
                          "thickness": 0.75, "value": 10},
            "bgcolor": "rgba(0,0,0,0)",
        },
    ))
    fig_g.update_layout(height=200, margin=dict(l=20,r=20,t=30,b=10),
                        paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#aaa"))
    st.plotly_chart(fig_g, use_container_width=True)

    if price_range > 0:
        pos = ((current_price - low_price) / price_range) * 100
        st.markdown(f"**Range Position:** `{pos:.1f}%`")
        st.progress(min(int(pos), 100))
        st.caption(f"${low_price:,.0f} — ${high_price:,.0f}")

st.markdown("---")
col_dist, col_analytics = st.columns(2)

with col_dist:
    st.markdown("#### Price Distribution")
    fig_h = go.Figure()
    fig_h.add_trace(go.Histogram(x=prices, nbinsx=30,
                                 marker_color="#4C9BE8", opacity=0.8))
    fig_h.add_vline(x=avg_price, line_dash="dash", line_color="#F5A623",
                    annotation_text="Mean")
    fig_h.update_layout(height=230, margin=dict(l=0,r=0,t=10,b=0),
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#aaa"), showlegend=False,
                        xaxis_title="Price (USDT)", yaxis_title="Count")
    st.plotly_chart(fig_h, use_container_width=True)

with col_analytics:
    st.markdown("#### Analytics Snapshot")
    if not analytics_df.empty:
        adf = analytics_df.sort_values("ts").tail(100)
        fig_a = go.Figure()
        if "volatility" in adf.columns:
            fig_a.add_trace(go.Scatter(x=adf["ts"], y=adf["volatility"],
                                       fill="tozeroy", fillcolor="rgba(232,112,58,0.2)",
                                       line=dict(color="#E8703A", width=1.5), name="Volatility σ"))
        if "z_score" in adf.columns:
            fig_a.add_trace(go.Scatter(x=adf["ts"], y=adf["z_score"].abs(),
                                       line=dict(color="#7ED321", width=1.5, dash="dot"),
                                       name="|Z-score|"))
        fig_a.update_layout(height=230, margin=dict(l=0,r=0,t=10,b=0),
                            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                            font=dict(color="#aaa"), legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_a, use_container_width=True)
    else:
        st.info("Analytics populate after ~20 ticks.")

st.markdown("---")
st.markdown("#### Executive Summary")
st.dataframe(pd.DataFrame({
    "Metric":  ["Current Price","Average Price","Session High","Session Low",
                "Price Range","Total Records","Anomalies","Anomaly Rate"],
    "Value":   [f"${current_price:,.2f}", f"${avg_price:,.2f}", f"${high_price:,.2f}",
                f"${low_price:,.2f}", f"${price_range:,.2f}", f"{total_records:,}",
                str(anomaly_count), f"{anomaly_rate:.2f}%"],
    "Status":  [
        "🔴 Above avg" if current_price > avg_price else "🟡 Below avg",
        "📊 Baseline", "📈 Peak", "📉 Trough",
        "🟢 Tight" if price_range < 500 else "🟠 Wide",
        "✅ Active",
        "🟢 Low" if anomaly_rate < 5 else "🔴 High",
        "✅ Normal" if anomaly_rate < 10 else "⚠️ Elevated",
    ],
}), use_container_width=True, hide_index=True)

time.sleep(refresh)
st.rerun()
