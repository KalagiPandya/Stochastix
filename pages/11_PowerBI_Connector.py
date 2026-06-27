"""pages/11_PowerBI_Connector.py — Power BI data export and dashboard preview."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import io
from datetime import datetime

from pipeline import init_db, fetch_recent_ticks, count_anomalies
from services.stream import start_stream
from services.analytics import sma, ema, volatility, z_score

st.set_page_config(page_title="Power BI — Stochastix", page_icon="🟡", layout="wide")

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
    st.markdown("## 🟡 Power BI Settings")
    symbols      = st.multiselect("Assets", ["BTCUSDT","ETHUSDT","SOLUSDT"],
                                  default=["BTCUSDT","ETHUSDT","SOLUSDT"])
    export_limit = st.selectbox("Records per asset", [100, 200, 500], index=1)

COLORS = {"BTCUSDT": "#F7931A", "ETHUSDT": "#627EEA", "SOLUSDT": "#9945FF"}

def enrich(symbol, limit):
    df = fetch_recent_ticks(symbol, limit=limit)
    if df.empty: return df
    df = df.sort_values("ts").reset_index(drop=True)
    p  = df["price"].tolist()
    df["symbol"]   = symbol
    df["sma_20"]   = [sma(p[:i+1], 20) for i in range(len(p))]
    df["ema_20"]   = [ema(p[:i+1], 20) for i in range(len(p))]
    df["vol"]      = [volatility(p[:i+1], 20) for i in range(len(p))]
    df["z"]        = [z_score(p[i], p[:i+1], 30) for i in range(len(p))]
    df["anomaly"]  = df["z"].apply(lambda z: abs(z) > 2.5 if z is not None else False)
    df["pct_chg"]  = df["price"].pct_change() * 100
    df["direction"]= np.where(df["pct_chg"] >= 0, "Up", "Down")
    df["hour"]     = pd.to_datetime(df["ts"]).dt.hour
    return df

st.title("🟡 Power BI Connector")
st.caption("Dashboard previews · Power BI-ready data export")

tab_exec, tab_trends, tab_anom, tab_export, tab_guide = st.tabs([
    "📊 Executive", "📈 Market Trends", "🚨 Anomaly", "💾 Export", "📋 Guide"
])

# ── Executive ──────────────────────────────────────────────────────────────
with tab_exec:
    st.markdown("### Executive Dashboard")
    dfs = [enrich(s, export_limit) for s in symbols]
    dfs = [d for d in dfs if not d.empty]
    if not dfs:
        st.info("⏳ Collecting data…")
    else:
        cols = st.columns(len(dfs))
        for col, df in zip(cols, dfs):
            sym = df["symbol"].iloc[0]
            p   = df["price"].tolist()
            with col:
                st.markdown(f"**{sym}**")
                st.metric("Current", f"${p[-1]:,.2f}",
                          f"{df['pct_chg'].iloc[-1]:+.3f}%")
                st.metric("Average",   f"${np.mean(p):,.2f}")
                st.metric("Anomalies", str(int(df["anomaly"].sum())))
        st.markdown("---")
        fig = go.Figure()
        for df in dfs:
            sym  = df["symbol"].iloc[0]
            base = df["price"].iloc[0]
            fig.add_trace(go.Scatter(
                x=df["ts"], y=(df["price"]-base)/base*100,
                name=sym, line=dict(color=COLORS.get(sym,"#4C9BE8"), width=2),
            ))
        fig.update_layout(height=320, yaxis_title="% Change from Start",
                          margin=dict(l=0,r=0,t=10,b=0),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#aaa"), legend=dict(orientation="h", y=1.1))
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
        st.plotly_chart(fig, use_container_width=True)

# ── Market Trends ──────────────────────────────────────────────────────────
with tab_trends:
    st.markdown("### Market Trends")
    dfs = [enrich(s, export_limit) for s in symbols]
    dfs = [d for d in dfs if not d.empty]
    if not dfs:
        st.info("⏳ Collecting data…")
    else:
        combined = pd.concat(dfs, ignore_index=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Volatility by Asset")
            vol_s = combined.groupby("symbol")["vol"].mean().reset_index()
            vol_s.columns = ["Symbol","Avg Volatility"]
            fig = px.bar(vol_s, x="Symbol", y="Avg Volatility",
                         color="Symbol", color_discrete_map=COLORS)
            fig.update_layout(height=260, margin=dict(l=0,r=0,t=10,b=0),
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font=dict(color="#aaa"), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.markdown("#### Up vs Down Distribution")
            dir_c = combined.groupby(["symbol","direction"]).size().reset_index(name="count")
            fig = px.bar(dir_c, x="symbol", y="count", color="direction",
                         barmode="group",
                         color_discrete_map={"Up":"#7ED321","Down":"#E8703A"})
            fig.update_layout(height=260, margin=dict(l=0,r=0,t=10,b=0),
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font=dict(color="#aaa"))
            st.plotly_chart(fig, use_container_width=True)

# ── Anomaly ────────────────────────────────────────────────────────────────
with tab_anom:
    st.markdown("### Anomaly Dashboard")
    dfs = [enrich(s, export_limit) for s in symbols]
    dfs = [d for d in dfs if not d.empty]
    if not dfs:
        st.info("⏳ Collecting data…")
    else:
        for df in dfs:
            sym   = df["symbol"].iloc[0]
            anom  = df[df["anomaly"]]
            norm  = df[~df["anomaly"]]
            st.markdown(f"#### {sym}")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=norm["ts"], y=norm["price"], mode="markers",
                                     name="Normal", marker=dict(color="#4C9BE8", size=4, opacity=0.5)))
            fig.add_trace(go.Scatter(x=anom["ts"], y=anom["price"], mode="markers",
                                     name="Anomaly", marker=dict(color="#E8703A", size=10, symbol="x",
                                                                  line=dict(color="#FF4444",width=2))))
            fig.add_trace(go.Scatter(x=df["ts"], y=df["sma_20"], name="SMA-20",
                                     line=dict(color="#F5A623", dash="dot", width=1.5)))
            fig.update_layout(height=250, margin=dict(l=0,r=0,t=10,b=0),
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font=dict(color="#aaa"), legend=dict(orientation="h", y=1.1))
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(gridcolor="rgba(128,128,128,0.1)")
            st.plotly_chart(fig, use_container_width=True)
            a1, a2, a3 = st.columns(3)
            a1.metric("Total Ticks", f"{len(df):,}")
            a2.metric("Anomalies",   str(len(anom)))
            a3.metric("Rate",        f"{len(anom)/len(df)*100:.2f}%" if len(df) else "—")
            st.markdown("---")

# ── Export ─────────────────────────────────────────────────────────────────
with tab_export:
    st.markdown("### Export for Power BI")
    st.info("Get Data → Excel Workbook in Power BI Desktop")
    dfs = [enrich(s, export_limit) for s in symbols]
    dfs = [d for d in dfs if not d.empty]
    if not dfs:
        st.warning("No data yet.")
    else:
        combined = pd.concat(dfs, ignore_index=True)
        ts_str   = datetime.now().strftime("%Y%m%d_%H%M%S")
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("**Fact Table (Prices)**")
            fact_cols = ["symbol","price","ts","pct_chg","direction"]
            if "volume" in combined.columns:
                fact_cols.insert(2, "volume")
            fact = combined[fact_cols].copy()
            st.download_button("⬇️ fact_prices.csv", fact.to_csv(index=False).encode(),
                               f"fact_prices_{ts_str}.csv", "text/csv", use_container_width=True)
        with c2:
            st.markdown("**Analytics Table**")
            anl  = combined[["symbol","ts","sma_20","ema_20","vol","z","anomaly"]].copy()
            st.download_button("⬇️ dim_analytics.csv", anl.to_csv(index=False).encode(),
                               f"dim_analytics_{ts_str}.csv", "text/csv", use_container_width=True)
        with c3:
            st.markdown("**KPI Summary**")
            rows = []
            for df in dfs:
                sym = df["symbol"].iloc[0]; p = df["price"].tolist()
                rows.append({"Symbol":sym,"Records":len(df),"Avg":round(np.mean(p),2),
                             "High":round(max(p),2),"Low":round(min(p),2),
                             "Anomalies":int(df["anomaly"].sum()),
                             "AnomalyRate%":round(df["anomaly"].mean()*100,2)})
            kpi_df = pd.DataFrame(rows)
            st.download_button("⬇️ summary_kpi.csv", kpi_df.to_csv(index=False).encode(),
                               f"summary_kpi_{ts_str}.csv", "text/csv", use_container_width=True)

        st.markdown("---")
        st.markdown("**Full Excel Pack**")
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            fact.to_excel(w, sheet_name="Fact_Prices",   index=False)
            anl.to_excel( w, sheet_name="Dim_Analytics", index=False)
            kpi_df.to_excel(w, sheet_name="Summary_KPI", index=False)
        buf.seek(0)
        st.download_button("⬇️ Download Full Power BI Pack (.xlsx)", buf.getvalue(),
                           f"stochastix_powerbi_{ts_str}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── Guide ──────────────────────────────────────────────────────────────────
with tab_guide:
    st.markdown("### Connection Guide")
    st.markdown("""
**Method 1 — Excel Pack (Recommended)**
1. Download the **Full Power BI Pack** from the Export tab
2. Power BI Desktop → Get Data → Excel Workbook
3. Select all 3 sheets: `Fact_Prices`, `Dim_Analytics`, `Summary_KPI`
4. Load → relate tables on `symbol` and `ts` in Model view

---

**Method 2 — CSV**
1. Download individual CSVs from the Export tab
2. Power BI → Get Data → Text/CSV → repeat for each file

---

**Recommended DAX Measures**
```
Avg Price    = AVERAGE(Fact_Prices[price])
Anomaly Rate = DIVIDE(
    COUNTROWS(FILTER(Dim_Analytics, Dim_Analytics[anomaly] = TRUE())),
    COUNTROWS(Dim_Analytics))
Price Range  = MAX(Fact_Prices[price]) - MIN(Fact_Prices[price])
```
""")