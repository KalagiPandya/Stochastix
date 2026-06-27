"""pages/4_Data_Explorer.py — Raw data browser and CSV export."""

import streamlit as st
import pandas as pd
import time

from pipeline import fetch_recent_ticks, fetch_analytics, fetch_candles, init_db
from services.stream import start_stream

st.set_page_config(page_title="Data Explorer — Stochastix", page_icon="🗄️", layout="wide")

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
    st.markdown("## 🗄️ Explorer Settings")
    symbol  = st.selectbox("Asset", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    view    = st.radio("Table", ["Tick Data", "Analytics Metrics", "OHLC Candles"])
    limit   = st.slider("Row limit", 50, 500, 100)
    refresh = st.slider("Refresh (s)", 1, 10, 5)

st.title("🗄️ Data Explorer")
st.caption(f"Live database view · `{symbol}`")

if view == "Tick Data":
    df = fetch_recent_ticks(symbol, limit=limit)
    if df.empty:
        st.info("No tick data yet.")
    else:
        df = df.sort_values("ts", ascending=False).reset_index(drop=True)
        st.markdown(f"**{len(df):,} ticks** stored")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("📥 Download CSV", df.to_csv(index=False),
                           f"{symbol}_ticks.csv", "text/csv")

elif view == "Analytics Metrics":
    df = fetch_analytics(symbol, limit=limit)
    if df.empty:
        st.info("No analytics data yet (need ~20 ticks).")
    else:
        df = df.sort_values("ts", ascending=False).reset_index(drop=True)
        st.markdown(f"**{len(df):,} metric rows**")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("📥 Download CSV", df.to_csv(index=False),
                           f"{symbol}_analytics.csv", "text/csv")

else:
    df = fetch_candles(symbol, limit=limit)
    if df.empty:
        st.info("No candles yet — builds after 1+ minute of streaming.")
    else:
        df = df.sort_values("candle_ts", ascending=False).reset_index(drop=True)
        st.markdown(f"**{len(df):,} 1-min candles**")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("📥 Download CSV", df.to_csv(index=False),
                           f"{symbol}_candles.csv", "text/csv")

st.markdown("---")
st.caption(f"DuckDB · stochastix.db · {pd.Timestamp.now().strftime('%H:%M:%S')}")

time.sleep(refresh)
st.rerun()
