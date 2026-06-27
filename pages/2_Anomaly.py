"""pages/2_Anomaly.py — Real-time Z-score anomaly detection."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import time

from pipeline import fetch_recent_ticks, count_anomalies, init_db
from services.stream import get_buffer, start_stream
from services.analytics import z_score, is_anomaly, sma, volatility

st.set_page_config(page_title="Anomaly Detection — Stochastix", page_icon="🚨", layout="wide")

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
    st.markdown("## 🚨 Detection Settings")
    symbol   = st.selectbox("Asset", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    z_window = st.slider("Z-score Window", 10, 60, 30)
    z_thresh = st.slider("Threshold |z|", 1.5, 4.0, 2.5, step=0.1)
    refresh  = st.slider("Refresh (s)", 1, 10, 3)

st.title("🚨 Anomaly Detection")
st.caption(f"Z-score based detection · `{symbol}` · window={z_window} · threshold=±{z_thresh}")

prices_buf = get_buffer(symbol)
ticks_df   = fetch_recent_ticks(symbol, limit=300)

if len(prices_buf) < z_window + 5:
    st.info(f"⏳ Collecting data — need {z_window + 5} ticks…"); time.sleep(2); st.rerun()

prices       = prices_buf
current      = prices[-1]
current_z    = z_score(current, prices, z_window)
anom_now     = is_anomaly(current_z, z_thresh)
anom_count   = count_anomalies(symbol, minutes=60)

c1, c2, c3, c4 = st.columns(4)
c1.metric("💰 Price",      f"${current:,.2f}")
c2.metric("📐 Z-score",    f"{current_z:.3f}" if current_z is not None else "—",
          delta="⚠️ ANOMALY" if anom_now else "Normal",
          delta_color="inverse" if anom_now else "normal")
c3.metric("🚨 Anomalies (1h)", str(anom_count))
c4.metric("🎯 Threshold",  f"±{z_thresh}")

if anom_now:
    direction = "SPIKE ▲" if (current_z or 0) > 0 else "DROP ▼"
    st.error(f"🚨 **{direction}**  |  Z = `{current_z:.3f}`  |  Price = `${current:,.2f}`")
else:
    st.success("✅ Market within normal statistical bounds")

st.markdown("---")

if not ticks_df.empty:
    ticks_df = ticks_df.sort_values("ts").reset_index(drop=True)
    p = ticks_df["price"].tolist()

    z_series = []
    for i in range(len(p)):
        if i < z_window:
            z_series.append(0.0)
        else:
            zv = z_score(p[i], p[:i], z_window)
            z_series.append(zv if zv is not None else 0.0)

    anom_mask   = [abs(z) > z_thresh for z in z_series]
    anom_prices = [p[i] if anom_mask[i] else None for i in range(len(p))]

    sma_v   = [sma(p[:i+1], z_window) or p[i] for i in range(len(p))]
    vol_s   = [volatility(p[:i+1], z_window) for i in range(len(p))]
    ub      = [u + z_thresh * v for u, v in zip(sma_v, vol_s)]
    lb      = [u - z_thresh * v for u, v in zip(sma_v, vol_s)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ticks_df["ts"], y=ticks_df["price"],
                             name="Price", line=dict(color="#4C9BE8", width=2)))
    fig.add_trace(go.Scatter(x=ticks_df["ts"], y=ub,
                             name=f"+{z_thresh}σ",
                             line=dict(color="rgba(232,76,61,0.5)", dash="dot", width=1)))
    fig.add_trace(go.Scatter(x=ticks_df["ts"], y=lb,
                             name=f"-{z_thresh}σ",
                             line=dict(color="rgba(232,76,61,0.5)", dash="dot", width=1),
                             fill="tonexty", fillcolor="rgba(232,76,61,0.05)"))
    fig.add_trace(go.Scatter(x=ticks_df["ts"], y=anom_prices,
                             name="Anomaly", mode="markers",
                             marker=dict(color="#E84C3D", size=12, symbol="star",
                                         line=dict(color="white", width=1))))
    fig.update_layout(title=f"{symbol} · Anomaly Detection",
                      height=420, margin=dict(l=0,r=0,t=40,b=0),
                      legend=dict(orientation="h", y=1.08),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#aaaaaa"), yaxis_title="Price (USDT)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
    st.plotly_chart(fig, use_container_width=True)

    # Z-score chart
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=ticks_df["ts"], y=z_series,
                              name="Z-score", line=dict(color="#A078E8", width=1.5),
                              fill="tozeroy", fillcolor="rgba(160,120,232,0.1)"))
    fig2.add_hline(y=z_thresh,  line_dash="dot", line_color="rgba(232,76,61,0.7)", annotation_text=f"+{z_thresh}")
    fig2.add_hline(y=-z_thresh, line_dash="dot", line_color="rgba(232,76,61,0.7)", annotation_text=f"-{z_thresh}")
    fig2.add_hline(y=0, line_color="rgba(128,128,128,0.3)", line_width=0.5)
    fig2.update_layout(height=200, margin=dict(l=0,r=0,t=10,b=0),
                       plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                       font=dict(color="#aaaaaa"), yaxis_title="Z-score", showlegend=False)
    fig2.update_xaxes(showgrid=False)
    fig2.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
    st.plotly_chart(fig2, use_container_width=True)

    events = [{"Time": ticks_df["ts"].iloc[i], "Price": f"${p[i]:,.2f}",
               "Z-score": f"{z_series[i]:.3f}",
               "Direction": "▲ Spike" if z_series[i] > 0 else "▼ Drop"}
              for i in range(len(p)) if anom_mask[i]]
    if events:
        st.markdown("#### 🚨 Anomaly Event Log")
        st.dataframe(pd.DataFrame(events[::-1]), use_container_width=True, hide_index=True)
    else:
        st.info("No anomalies in current session data.")

time.sleep(refresh)
st.rerun()
