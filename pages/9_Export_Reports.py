"""pages/9_Export_Reports.py — CSV & Excel export."""

import streamlit as st
import pandas as pd
import io
from datetime import datetime

from pipeline import init_db, fetch_recent_ticks, fetch_analytics, count_anomalies
from services.stream import start_stream

st.set_page_config(page_title="Export Reports — Stochastix", page_icon="📤", layout="wide")

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
    st.markdown("## 📤 Export Settings")
    symbol      = st.selectbox("Asset", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    export_limit= st.selectbox("Records", [50, 100, 200, 500], index=1)
    inc_analytics = st.checkbox("Include Analytics", value=True)
    inc_kpis    = st.checkbox("Include KPI Summary", value=True)

st.title("📤 Export Reports")
st.caption(f"Download data for `{symbol}`")

ticks_df     = fetch_recent_ticks(symbol, limit=export_limit)
analytics_df = fetch_analytics(symbol, limit=export_limit)
anomaly_count= count_anomalies(symbol, minutes=60)
ts           = datetime.now().strftime("%Y%m%d_%H%M%S")

tab1, tab2, tab3 = st.tabs(["📊 Market Data", "🔬 Analytics", "📋 KPI Summary"])

with tab1:
    if not ticks_df.empty:
        st.dataframe(ticks_df, use_container_width=True, hide_index=True)
        st.caption(f"{len(ticks_df):,} records")
    else:
        st.info("No data yet.")

with tab2:
    if not analytics_df.empty:
        st.dataframe(analytics_df, use_container_width=True, hide_index=True)
    else:
        st.info("Analytics populate after ML processing begins.")

with tab3:
    if not ticks_df.empty:
        prices = ticks_df["price"].tolist()
        st.dataframe(pd.DataFrame({
            "Metric": ["Asset","Records","Avg Price","High","Low","Range","Anomalies (1h)","Generated"],
            "Value":  [symbol, len(ticks_df), f"${sum(prices)/len(prices):,.2f}",
                       f"${max(prices):,.2f}", f"${min(prices):,.2f}",
                       f"${max(prices)-min(prices):,.2f}", str(anomaly_count),
                       datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        }), use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("### 💾 Download")
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown("**Market Data CSV**")
    if not ticks_df.empty:
        st.download_button("⬇️ Export CSV", ticks_df.to_csv(index=False).encode(),
                           f"{symbol}_market_{ts}.csv", "text/csv", use_container_width=True)
    else:
        st.button("⬇️ Export CSV", disabled=True, use_container_width=True)

with c2:
    st.markdown("**Analytics CSV**")
    if not analytics_df.empty:
        st.download_button("⬇️ Export CSV", analytics_df.to_csv(index=False).encode(),
                           f"{symbol}_analytics_{ts}.csv", "text/csv", use_container_width=True)
    else:
        st.button("⬇️ Export CSV", disabled=True, use_container_width=True)

with c3:
    st.markdown("**Excel Workbook**")
    if not ticks_df.empty:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            ticks_df.to_excel(w, sheet_name="Market Data", index=False)
            if not analytics_df.empty and inc_analytics:
                analytics_df.to_excel(w, sheet_name="Analytics", index=False)
            if inc_kpis:
                prices = ticks_df["price"].tolist()
                pd.DataFrame({
                    "Metric": ["Asset","Records","Avg","High","Low","Anomalies"],
                    "Value":  [symbol, len(ticks_df), round(sum(prices)/len(prices),2),
                               round(max(prices),2), round(min(prices),2), anomaly_count],
                }).to_excel(w, sheet_name="KPI Summary", index=False)
        buf.seek(0)
        st.download_button("⬇️ Export Excel", buf.getvalue(),
                           f"{symbol}_report_{ts}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
    else:
        st.button("⬇️ Export Excel", disabled=True, use_container_width=True)

with c4:
    st.markdown("**Full Report (All Assets)**")
    buf2 = io.BytesIO()
    any_data = False
    summary_rows = []
    with pd.ExcelWriter(buf2, engine="openpyxl") as w:
        for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
            df = fetch_recent_ticks(sym, limit=export_limit)
            if not df.empty:
                df.to_excel(w, sheet_name=sym, index=False)
                any_data = True
                p = df["price"].tolist()
                summary_rows.append({"Symbol": sym, "Records": len(df),
                                     "Avg": round(sum(p)/len(p),2),
                                     "High": round(max(p),2), "Low": round(min(p),2),
                                     "Anomalies": count_anomalies(sym, 60)})
        if summary_rows:
            pd.DataFrame(summary_rows).to_excel(w, sheet_name="Summary", index=False)
    buf2.seek(0)
    if any_data:
        st.download_button("⬇️ Full Report", buf2.getvalue(),
                           f"stochastix_full_{ts}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
    else:
        st.button("⬇️ Full Report", disabled=True, use_container_width=True)

st.markdown("---")
st.caption("Filenames include timestamp · Supports CSV and Excel (.xlsx)")
