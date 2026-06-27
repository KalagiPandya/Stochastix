"""pages/8_SQL_Analytics.py — Advanced SQL Analytics with window functions."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from pipeline import init_db, DB_BACKEND
from pipeline.database import _query
from services.stream import start_stream

st.set_page_config(page_title="SQL Analytics — Stochastix", page_icon="🗄️", layout="wide")

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
    st.markdown("## 🗄️ SQL Analytics")
    selected = st.radio("Query", [
        "Top Volatile Coins",
        "Hourly Average Prices",
        "Moving Averages (Window)",
        "Price Rankings",
        "Window Functions: LAG / LEAD",
        "Anomaly Summary",
    ])
    limit = st.slider("Row limit", 10, 100, 25)
    st.markdown("---")
    st.caption(f"Backend: **{DB_BACKEND.upper()}**")
    st.caption("All queries: CTEs · window functions · aggregations")

st.title("🗄️ Advanced SQL Analytics")
st.caption("Window functions · CTEs · Rankings · Aggregations")

def run(sql, params=None):
    try:
        return _query(sql, params)
    except Exception as e:
        st.error(f"Query error: {e}")
        return pd.DataFrame()

def show_sql(sql):
    with st.expander("View SQL", expanded=False):
        st.code(sql.strip(), language="sql")

# ── Query routing ──────────────────────────────────────────────────────────
if selected == "Top Volatile Coins":
    st.subheader("Top Volatile Coins")
    st.caption("RANK() over STDDEV — core volatility metric")
    sql = """
WITH stats AS (
    SELECT symbol,
           COUNT(*)                                AS tick_count,
           ROUND(AVG(price)::NUMERIC, 2)           AS avg_price,
           ROUND(STDDEV(price)::NUMERIC, 2)        AS std_dev,
           ROUND(MIN(price)::NUMERIC, 2)           AS min_price,
           ROUND(MAX(price)::NUMERIC, 2)           AS max_price,
           ROUND((MAX(price)-MIN(price))::NUMERIC, 2) AS price_range
    FROM market_data GROUP BY symbol
),
ranked AS (
    SELECT *, RANK() OVER (ORDER BY std_dev DESC) AS vol_rank,
           ROUND((std_dev / NULLIF(avg_price,0) * 100)::NUMERIC, 4) AS cv_pct
    FROM stats
)
SELECT vol_rank AS "Rank", symbol AS "Symbol", tick_count AS "Ticks",
       avg_price AS "Avg ($)", std_dev AS "Std Dev σ",
       min_price AS "Min ($)", max_price AS "Max ($)",
       price_range AS "Range ($)", cv_pct AS "CV %"
FROM ranked ORDER BY vol_rank LIMIT ?"""
    show_sql(sql)
    df = run(sql, [limit])
    if not df.empty:
        c1, c2 = st.columns([2,1])
        with c1: st.dataframe(df, use_container_width=True, hide_index=True)
        with c2:
            fig = px.bar(df, x="Symbol", y="Std Dev σ",
                         color="Std Dev σ", color_continuous_scale="Reds")
            fig.update_layout(height=280, margin=dict(l=0,r=0,t=10,b=0),
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font=dict(color="#aaa"), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet — stream populates shortly.")

elif selected == "Hourly Average Prices":
    st.subheader("Hourly Average Prices")
    st.caption("DATE_TRUNC hourly OHLC aggregation")
    sql = """
SELECT DATE_TRUNC('hour', ts)           AS "Hour",
       symbol                           AS "Symbol",
       COUNT(*)                         AS "Ticks",
       ROUND(AVG(price)::NUMERIC, 2)    AS "Avg ($)",
       ROUND(MIN(price)::NUMERIC, 2)    AS "Low ($)",
       ROUND(MAX(price)::NUMERIC, 2)    AS "High ($)",
       ROUND(STDDEV(price)::NUMERIC, 2) AS "Std Dev",
       ROUND(SUM(volume)::NUMERIC, 4)   AS "Volume"
FROM market_data
GROUP BY DATE_TRUNC('hour', ts), symbol
ORDER BY "Hour" DESC LIMIT ?"""
    show_sql(sql)
    df = run(sql, [limit])
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        if "Symbol" in df.columns:
            fig = go.Figure()
            for sym in df["Symbol"].unique():
                sdf = df[df["Symbol"]==sym].sort_values("Hour")
                fig.add_trace(go.Scatter(x=sdf["Hour"], y=sdf["Avg ($)"],
                                         mode="lines+markers", name=sym))
            fig.update_layout(height=280, margin=dict(l=0,r=0,t=10,b=0),
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font=dict(color="#aaa"))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

elif selected == "Moving Averages (Window)":
    st.subheader("Moving Averages — SQL Window Functions")
    st.caption("AVG OVER (ROWS BETWEEN) for SMA-7 and SMA-20, plus LAG price change")
    sql = """
WITH ordered AS (
    SELECT id, symbol, price, ts,
           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts) AS rn
    FROM market_data
),
ma AS (
    SELECT symbol, ts, price, rn,
           ROUND(AVG(price) OVER (PARTITION BY symbol ORDER BY rn
                 ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)::NUMERIC, 2) AS sma_7,
           ROUND(AVG(price) OVER (PARTITION BY symbol ORDER BY rn
                 ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)::NUMERIC, 2) AS sma_20,
           ROUND((price - LAG(price,1) OVER (PARTITION BY symbol ORDER BY rn))::NUMERIC, 4)
                 AS price_chg,
           ROUND(((price - LAG(price,1) OVER (PARTITION BY symbol ORDER BY rn))
                  / NULLIF(LAG(price,1) OVER (PARTITION BY symbol ORDER BY rn),0)*100
                 )::NUMERIC, 4) AS pct_chg
    FROM ordered
)
SELECT symbol AS "Symbol", ts AS "Timestamp",
       price AS "Price ($)", sma_7 AS "SMA-7", sma_20 AS "SMA-20",
       price_chg AS "Δ Price", pct_chg AS "Δ %"
FROM ma WHERE rn > 20 ORDER BY ts DESC LIMIT ?"""
    show_sql(sql)
    df = run(sql, [limit])
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        chart = df.sort_values("Timestamp")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=chart["Timestamp"], y=chart["Price ($)"],
                                 name="Price", line=dict(color="#4C9BE8", width=2)))
        if "SMA-7" in chart.columns:
            fig.add_trace(go.Scatter(x=chart["Timestamp"], y=chart["SMA-7"],
                                     name="SMA-7", line=dict(color="#F5A623", dash="dot")))
        if "SMA-20" in chart.columns:
            fig.add_trace(go.Scatter(x=chart["Timestamp"], y=chart["SMA-20"],
                                     name="SMA-20", line=dict(color="#7ED321", dash="dash")))
        fig.update_layout(height=300, margin=dict(l=0,r=0,t=10,b=0),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#aaa"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Need 20+ ticks per symbol.")

elif selected == "Price Rankings":
    st.subheader("Price Rankings")
    st.caption("RANK · DENSE_RANK · NTILE · PERCENT_RANK")
    sql = """
WITH all_prices AS (
    SELECT symbol, price, ts,
           RANK()         OVER (ORDER BY price DESC) AS price_rank,
           DENSE_RANK()   OVER (ORDER BY price DESC) AS dense_rank,
           PERCENT_RANK() OVER (ORDER BY price)      AS pct_rank,
           NTILE(4)       OVER (ORDER BY price DESC) AS quartile
    FROM market_data ORDER BY ts DESC LIMIT 200
)
SELECT symbol AS "Symbol",
       ROUND(price::NUMERIC, 2) AS "Price ($)",
       price_rank AS "Rank", dense_rank AS "Dense Rank",
       ROUND((pct_rank*100)::NUMERIC, 1) AS "Percentile",
       CASE quartile
           WHEN 1 THEN 'Top 25%' WHEN 2 THEN 'Top 50%'
           WHEN 3 THEN 'Top 75%' ELSE 'Bottom 25%'
       END AS "Quartile"
FROM all_prices LIMIT ?"""
    show_sql(sql)
    df = run(sql, [limit])
    if not df.empty: st.dataframe(df, use_container_width=True, hide_index=True)
    else: st.info("No data yet.")

elif selected == "Window Functions: LAG / LEAD":
    st.subheader("LAG · LEAD · Cumulative Window Functions")
    st.caption("Time-series comparison and running totals")
    sql = """
WITH ordered AS (
    SELECT symbol, price, volume, ts,
           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts) AS rn
    FROM market_data
)
SELECT symbol AS "Symbol", ts AS "Timestamp",
       ROUND(price::NUMERIC, 2) AS "Price ($)",
       ROUND(LAG(price,1)  OVER (PARTITION BY symbol ORDER BY rn)::NUMERIC, 2) AS "Prev",
       ROUND(LEAD(price,1) OVER (PARTITION BY symbol ORDER BY rn)::NUMERIC, 2) AS "Next",
       ROUND((price - LAG(price,1) OVER (PARTITION BY symbol ORDER BY rn))::NUMERIC, 2) AS "Δ ($)",
       ROUND(SUM(price)  OVER (PARTITION BY symbol ORDER BY rn
                               ROWS UNBOUNDED PRECEDING)::NUMERIC / rn, 2) AS "Cum Avg",
       ROUND(SUM(volume) OVER (PARTITION BY symbol ORDER BY rn
                               ROWS UNBOUNDED PRECEDING)::NUMERIC, 4) AS "Cum Vol",
       rn AS "Tick #"
FROM ordered ORDER BY ts DESC LIMIT ?"""
    show_sql(sql)
    df = run(sql, [limit])
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        if "Δ ($)" in df.columns:
            fig = px.histogram(df, x="Δ ($)", nbins=20,
                               color_discrete_sequence=["#4C9BE8"],
                               title="Price Change Distribution")
            fig.update_layout(height=250, margin=dict(l=0,r=0,t=40,b=0),
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font=dict(color="#aaa"))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

else:  # Anomaly Summary
    st.subheader("Anomaly Detection Summary")
    st.caption("Grouped by minute with z-score and ML score stats")
    sql = """
SELECT symbol AS "Symbol",
       DATE_TRUNC('minute', ts) AS "Minute",
       COUNT(*) AS "Checks",
       SUM(CASE WHEN anomaly_flag THEN 1 ELSE 0 END) AS "Anomalies",
       ROUND(AVG(ABS(z_score))::NUMERIC, 3) AS "Avg |Z|",
       ROUND(MAX(ABS(z_score))::NUMERIC, 3) AS "Max |Z|",
       ROUND(AVG(ml_score)::NUMERIC, 3)     AS "Avg ML Score"
FROM analytics_metrics
GROUP BY symbol, DATE_TRUNC('minute', ts)
ORDER BY "Minute" DESC LIMIT ?"""
    show_sql(sql)
    df = run(sql, [limit])
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        if "Anomalies" in df.columns:
            df["Rate %"] = (df["Anomalies"] / df["Checks"].replace(0,1) * 100).round(1)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df["Minute"], y=df["Rate %"],
                                 marker_color="#E8703A", name="Anomaly Rate %"))
            fig.update_layout(height=250, margin=dict(l=0,r=0,t=10,b=0),
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font=dict(color="#aaa"))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No analytics data yet.")

st.markdown("---")
st.caption("Window functions: RANK · DENSE_RANK · NTILE · PERCENT_RANK · LAG · LEAD · AVG OVER · SUM OVER")
