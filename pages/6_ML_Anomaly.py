"""pages/6_ML_Anomaly.py — ML-based anomaly detection (analyst+ only)."""

import time
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pipeline import init_db, fetch_recent_ticks
from services.stream import get_buffer, start_stream
from services.analytics import z_score, is_anomaly
from services.ml_anomaly import get_ml_ensemble
from services.streaming_backbone import get_backbone
from auth.security import require_role

st.set_page_config(page_title="ML Anomaly — Stochastix", page_icon="🤖", layout="wide")

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

user = require_role("analyst")

with st.sidebar:
    st.markdown(f"👤 **{user['username']}** ({user['role']})")
    symbol  = st.selectbox("Asset", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    refresh = st.slider("Refresh (s)", 2, 15, 5)
    st.caption("Models re-train on the live buffer — no historical data needed.")

st.title("🤖 ML Anomaly Detection")
st.caption(f"Isolation Forest · Prophet · LSTM Autoencoder · `{symbol}`")

prices   = get_buffer(symbol)
ticks_df = fetch_recent_ticks(symbol, limit=300)

if len(prices) < 60:
    st.info("⏳ ML models need a larger warm-up window (60 ticks).")
    time.sleep(2); st.rerun()

ensemble = get_ml_ensemble()
results  = ensemble.score_all(symbol, prices)
vote     = ensemble.ensemble_vote(results)

current  = prices[-1]
current_z = z_score(current, prices, 30)
stat_anom = is_anomaly(current_z, 2.5)

backbone = get_backbone()
if vote["anomaly"]:
    backbone.publish_anomaly(symbol, price=current,
                             ensemble_votes=vote["votes"],
                             ensemble_of=vote["of"],
                             avg_score=vote["avg_score"],
                             methods={n: r.is_anomaly for n, r in results.items()})

c1, c2, c3, c4 = st.columns(4)
c1.metric("💰 Price", f"${current:,.2f}")
c2.metric("📐 Z-score", f"{current_z:.3f}" if current_z is not None else "—",
          delta="⚠️ Anomaly" if stat_anom else "Normal",
          delta_color="inverse" if stat_anom else "normal")
c3.metric("🗳️ ML Ensemble", f"{vote['votes']} / {vote['of']}",
          delta="⚠️ Anomaly" if vote["anomaly"] else "Normal",
          delta_color="inverse" if vote["anomaly"] else "normal")
c4.metric("📊 Avg Score", f"{vote['avg_score']:.3f}")

if vote["anomaly"]:
    st.error(f"🚨 **ML Ensemble Alert** — {vote['votes']}/{vote['of']} models flagged anomaly.")
elif vote["of"] == 0:
    st.warning("No ML detectors available. Install optional deps below.")
else:
    st.success("✅ ML ensemble: normal market behaviour.")

st.markdown("---")
st.markdown("### 🔬 Per-Model Breakdown")

labels = {
    "isolation_forest":  ("🌲 Isolation Forest",  "Unsupervised outlier on [price, return, volatility] features."),
    "prophet":           ("📈 Prophet",            "Forecast-band deviation — flags prices outside expected trend."),
    "lstm_autoencoder":  ("🧠 LSTM Autoencoder",   "Sequence reconstruction error — flags unusual price patterns."),
}
cols = st.columns(3)
for col, (key, (label, desc)) in zip(cols, labels.items()):
    r = results.get(key)
    with col:
        st.markdown(f"#### {label}")
        st.caption(desc)
        if r is None or not r.available:
            st.info("Not installed. See dependencies below.")
            continue
        if r.error:
            st.error(f"Error: {r.error}"); continue
        reason = r.detail.get("reason", "")
        if reason == "insufficient_data":
            st.info(f"Warming up — need {r.detail.get('need','more')} ticks."); continue
        if reason == "model_not_yet_trained":
            st.info("Training in progress…"); continue
        st.metric("Status", "🚨 ANOMALY" if r.is_anomaly else "✅ Normal")
        st.metric("Score",  f"{r.score:.3f}")
        with st.expander("Details"):
            st.json(r.detail)

st.markdown("---")

if not ticks_df.empty:
    ticks_df = ticks_df.sort_values("ts").reset_index(drop=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ticks_df["ts"], y=ticks_df["price"],
                             name="Price", line=dict(color="#4C9BE8", width=2)))
    if vote["anomaly"]:
        fig.add_trace(go.Scatter(x=[ticks_df["ts"].iloc[-1]], y=[current],
                                 name="ML Anomaly", mode="markers",
                                 marker=dict(color="#E84C3D", size=16, symbol="star",
                                             line=dict(color="white", width=2))))
    fig.update_layout(title=f"{symbol} · ML Anomaly Flag",
                      height=380, margin=dict(l=0,r=0,t=40,b=0),
                      legend=dict(orientation="h", y=1.08),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#aaaaaa"), yaxis_title="Price (USDT)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
    st.plotly_chart(fig, use_container_width=True)

with st.expander("📦 Optional dependencies for full ML coverage"):
    st.code("pip install scikit-learn prophet torch", language="bash")
    st.caption("scikit-learn → Isolation Forest  |  prophet → forecast detector  |  torch → LSTM")

time.sleep(refresh)
st.rerun()
