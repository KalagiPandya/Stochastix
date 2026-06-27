<div align="center">

<!--  ╔══════════════════════════════════════════════════════════╗
      ║              STOCHASTIX  —  HERO HEADER                 ║
      ╚══════════════════════════════════════════════════════════╝  -->

<img src="https://capsule-render.vercel.app/api?type=venom&color=0:0d0221,30:1a0533,60:2d1b69,85:4c1d95,100:7c3aed&height=260&section=header&text=STOCHASTIX&fontSize=72&fontColor=e9d5ff&fontAlignY=42&desc=Real-Time%20Financial%20Analytics%20%E2%80%94%20Crypto%20Streams%20%C2%B7%20ML%20Anomaly%20Detection%20%C2%B7%20Cloud%20Native&descAlignY=65&descSize=15&fontStyle=bold&animation=twinkling" width="100%"/>

<br/>

<!-- ── Core Stack Badges ── -->
[![Python](https://img.shields.io/badge/Python_3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit_1.35-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io)
[![DuckDB](https://img.shields.io/badge/DuckDB-Local_Dev-FFC832?style=flat-square&logo=duckdb&logoColor=black)](https://duckdb.org)
[![TimescaleDB](https://img.shields.io/badge/TimescaleDB-Production-336791?style=flat-square&logo=postgresql&logoColor=white)](https://www.timescale.com)
[![Kafka](https://img.shields.io/badge/Apache_Kafka-231F20?style=flat-square&logo=apachekafka&logoColor=white)](https://kafka.apache.org)
[![Redis](https://img.shields.io/badge/Redis_Streams-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)

<!-- ── Quality & Deployment Badges ── -->
[![Tests](https://img.shields.io/badge/Tests-56_Passing-6d28d9?style=flat-square&logo=pytest&logoColor=white)](tests/)
[![Docker](https://img.shields.io/badge/Docker_Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![AWS](https://img.shields.io/badge/AWS_Fargate-FF9900?style=flat-square&logo=amazonaws&logoColor=white)](deploy/aws)
[![GCP](https://img.shields.io/badge/GCP_Cloud_Run-4285F4?style=flat-square&logo=googlecloud&logoColor=white)](deploy/gcp)
[![Azure](https://img.shields.io/badge/Azure_Container_Apps-0078D4?style=flat-square&logo=microsoftazure&logoColor=white)](deploy/azure)
[![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub_Actions-7c3aed?style=flat-square&logo=githubactions&logoColor=white)](.github/workflows)

<br/>

> **Stochastix** streams live crypto ticks from Binance, runs a statistical + ML anomaly detection ensemble on every event, persists everything to a time-series database, and surfaces it all across **11 Streamlit dashboard pages** — structured the way a real production data pipeline would be.

<br/>

</div>

---

## ⚡ Quick Start

```bash
git clone https://github.com/<you>/Stochastix.git
cd Stochastix

python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements-core.txt              # lean build — no Prophet / LSTM

streamlit run app.py
# → http://localhost:8501   |   No .env needed   |   Runs on DuckDB out of the box
```

Full ML stack (Prophet + LSTM Autoencoder):
```bash
pip install -r requirements.txt
```

---

## 🏗️ Architecture

```
Binance WebSocket  ──►  services/stream.py            ← live tick ingestion + ring buffer
                              │
               ┌──────────────┼───────────────────────┐
               ▼              ▼                       ▼
    services/analytics.py   services/ml_anomaly.py   services/streaming_backbone.py
    SMA · EMA · Bollinger    Isolation Forest          Kafka  or  Redis Streams
    Z-score · ROC            Prophet · LSTM            (every tick published to topics)
               │
               ▼
          pipeline/                                   ← DuckDB  or  PostgreSQL/TimescaleDB
               │
               └──►  auth/security.py                ← JWT + bcrypt + RBAC
```

---

## ✨ Feature Highlights

| Category | What's Inside |
|---|---|
| 📡 **Live Ingestion** | Binance `@trade` WebSocket with REST fallback and auto-reconnect |
| 📊 **Statistics** | Rolling SMA, EMA, Bollinger Bands, Z-score, Rate-of-Change |
| 🤖 **ML Ensemble** | Isolation Forest + Prophet forecast bands + LSTM Autoencoder — majority-vote verdict |
| 🗄️ **Dual Database** | DuckDB for zero-config local dev; PostgreSQL + TimescaleDB for production (one env var to switch) |
| 🔀 **Message Streaming** | Apache Kafka or Redis Streams backbone; ticks, metrics, and anomaly events each get their own topic |
| 🔐 **Auth & RBAC** | JWT access tokens, bcrypt password hashing, `admin / analyst / viewer` role gates on every page |
| 📈 **12 Dashboard Pages** | OHLC candles, KPI cards, SQL analytics, forecasting, Power BI export, and more |
| 📤 **Reporting** | CSV and Excel export; Power BI-ready data pack with three relational sheets |
| 🐳 **Docker** | Multi-stage build; Compose profiles for Postgres, Redis, and Kafka |
| ☁️ **Cloud** | AWS ECS Fargate (+ Terraform), GCP Cloud Run, Azure Container Apps — same image, same env vars |
| 🧪 **Tests** | 56 pytest tests across analytics, ML, streaming, and auth |

---

## 📊 Dashboard Pages

| # | Page | Role | Description |
|---|---|---|---|
| 🏠 | **Home** | viewer | Live ticker tape, SMA/EMA price overlay, anomaly alert banner |
| 1 | **Volatility** | viewer | Bollinger Bands, rolling volatility, market-regime classifier |
| 2 | **Anomaly** | viewer | Z-score series, threshold bands, anomaly event log |
| 3 | **Comparison** | viewer | Normalised % performance across BTC/ETH/SOL, OHLC candlesticks, metrics table |
| 4 | **Data Explorer** | viewer | Browse and export raw ticks, computed metrics, and candles |
| 5 | **Login** | public | Sign in, register, JWT token viewer, RBAC capability matrix |
| 6 | **ML Anomaly** | analyst+ | Isolation Forest, Prophet, and LSTM scores with majority-vote ensemble |
| 7 | **KPI Dashboard** | viewer | Executive KPI cards, anomaly-rate gauge, price distribution chart |
| 8 | **SQL Analytics** | viewer | 6 advanced queries — window functions, CTEs, rankings, moving averages |
| 9 | **Export Reports** | viewer | Download market data and analytics as CSV or Excel |
| 10 | **Forecasting** | viewer | Linear regression + EMA forecast with confidence bands |
| 11 | **Power BI Connector** | viewer | Dashboard previews and Power BI-ready data export pack |

---

## ⚙️ Configuration

All enterprise features are opt-in via `.env`. The app runs without any of these set.

**PostgreSQL + TimescaleDB**
```bash
DB_BACKEND=postgres
POSTGRES_HOST=localhost
POSTGRES_DB=stochastix
POSTGRES_USER=stochastix
POSTGRES_PASSWORD=change-me
POSTGRES_RETENTION_DAYS=30
```

**Kafka or Redis Streams**
```bash
# Kafka
STREAM_BACKEND=kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Redis
STREAM_BACKEND=redis
REDIS_URL=redis://localhost:6379/0
```

**Authentication**
```bash
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
DEFAULT_ADMIN_USER=admin
DEFAULT_ADMIN_PASSWORD=change-me
```

**RBAC Roles**

| Role | Access |
|---|---|
| `viewer` | All read-only dashboards |
| `analyst` | + ML Anomaly page, full data export |
| `admin` | + user management, full configuration |

---

## 🐳 Docker

```bash
# Default — DuckDB, no extras
docker compose up --build

# With TimescaleDB + Redis
docker compose --profile postgres --profile redis up --build

# With TimescaleDB + Kafka
docker compose --profile postgres --profile kafka up --build
```

---

## ☁️ Cloud Deployment

Same Docker image and env vars across all three providers.

| Cloud | Service | IaC |
|---|---|---|
| **AWS** | ECS Fargate + ALB + RDS + ElastiCache | Terraform included — [`deploy/aws`](deploy/aws/README.md) |
| **GCP** | Cloud Run + Cloud SQL + Memorystore | CLI guide — [`deploy/gcp`](deploy/gcp/README.md) |
| **Azure** | Container Apps + Azure DB for PostgreSQL + Azure Cache | CLI guide — [`deploy/azure`](deploy/azure/README.md) |

```bash
# AWS one-liner
cd deploy/aws/terraform
terraform init && terraform apply \
  -var="image_url=<ecr-uri>" \
  -var="jwt_secret_key=$(python -c 'import secrets; print(secrets.token_hex(32))')"
```

---

## 🧠 Algorithms

| Algorithm | How It Works |
|---|---|
| **SMA / EMA** | Simple and exponential moving averages over configurable windows |
| **Bollinger Bands** | SMA ± 2 standard deviations — squeeze/expansion regime detection |
| **Rolling Z-score** | Statistical distance from the rolling mean, configurable threshold |
| **Isolation Forest** | Unsupervised outlier detection on price, return, and volatility features |
| **Prophet** | Forecast-band anomaly — flags prices outside the expected trend range |
| **LSTM Autoencoder** | Reconstruction error on 20-tick sliding windows — high error signals anomaly |
| **Majority-Vote Ensemble** | Final label is the majority verdict across all three ML models |

---

## 🗄️ Database Schema

Four tables — schema is identical across DuckDB and TimescaleDB:

| Table | Contents |
|---|---|
| `market_data` | Raw ticks: symbol, price, volume, timestamp |
| `analytics_metrics` | SMA, EMA, Z-score, anomaly flag, and ML score per tick |
| `ohlc_candles` | 1-minute aggregated OHLC + volume |
| `users` | Username, bcrypt hash, role, active flag |

On TimescaleDB all three time-series tables are promoted to hypertables with automatic compression after one day and a configurable data-retention policy.

---

## 📤 Power BI Setup

1. Open the app → **Power BI Connector** page → download the **Full Power BI Pack (.xlsx)**
2. Three sheets inside: `Fact_Prices`, `Dim_Analytics`, `Summary_KPI`
3. In Power BI Desktop: **Get Data → Excel Workbook** → select all three sheets → Load
4. Relate tables on `symbol` and `ts` in Model view

Key DAX measures:
```
Avg Price     = AVERAGE(Fact_Prices[price])
Anomaly Rate  = DIVIDE(COUNTROWS(FILTER(Dim_Analytics, Dim_Analytics[anomaly] = TRUE())), COUNTROWS(Dim_Analytics))
Price Range   = MAX(Fact_Prices[price]) - MIN(Fact_Prices[price])
Current Price = LASTNONBLANK(Fact_Prices[price], 1)
```

---

## 🧪 Tests

```bash
pytest tests/ -v
```

```
tests/test_analytics.py              30 passed
tests/test_auth.py                    9 passed
tests/test_ml_anomaly.py             12 passed
tests/test_streaming_backbone.py      5 passed
──────────────────────────────────────────────
56 passed in total
```

---

## 🗂️ Project Structure

```
Stochastix/
├── app.py                          ← Home dashboard (entry point)
├── pages/
│   ├── 1_Volatility.py             ← Bollinger Bands, volatility regimes
│   ├── 2_Anomaly.py                ← Z-score anomaly detection
│   ├── 3_Comparison.py             ← Multi-asset OHLC comparison
│   ├── 4_Data_Explorer.py          ← Browse and export raw data
│   ├── 5_Login.py                  ← Auth, register, RBAC matrix
│   ├── 6_ML_Anomaly.py             ← Isolation Forest, Prophet, LSTM  [analyst+]
│   ├── 7_KPI_Dashboard.py          ← Business KPI metrics, anomaly gauge
│   ├── 8_SQL_Analytics.py          ← Window functions, CTEs, rankings
│   ├── 9_Export_Reports.py         ← CSV and Excel export
│   ├── 10_Forecasting.py           ← Linear regression + EMA forecasts
│   └── 11_PowerBI_Connector.py     ← Power BI dashboards and data export
├── services/
│   ├── analytics.py                ← SMA, EMA, volatility, Z-score, ROC
│   ├── stream.py                   ← Binance WebSocket ingestion + buffer
│   ├── streaming_backbone.py       ← Kafka / Redis Streams publisher
│   └── ml_anomaly.py               ← ML ensemble (IF, Prophet, LSTM)
├── pipeline/
│   ├── __init__.py                 ← DB_BACKEND switcher
│   ├── database.py                 ← DuckDB backend
│   └── postgres_db.py              ← PostgreSQL + TimescaleDB backend
├── auth/
│   └── security.py                 ← JWT, bcrypt, RBAC, role guard
├── deploy/
│   ├── aws/                        ← ECS Fargate + Terraform
│   ├── gcp/                        ← Cloud Run
│   └── azure/                      ← Container Apps
├── tests/                          ← 56 pytest tests
├── .github/workflows/ci-cd.yml     ← lint → test → build → publish → deploy
├── Dockerfile
├── docker-compose.yml
├── requirements.txt                ← Full (all ML deps)
├── requirements-core.txt           ← Lean (sklearn only)
└── .env.example
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Dashboard | Streamlit + Plotly |
| Data Ingest | Binance WebSocket (`websocket-client`) + REST fallback |
| Message Streaming | Apache Kafka · Redis Streams |
| Database | DuckDB (dev) · PostgreSQL + TimescaleDB (prod) |
| Analytics | NumPy · Pandas |
| ML | scikit-learn · Prophet · PyTorch (LSTM) |
| Auth | PyJWT · bcrypt |
| Reporting | openpyxl · Power BI (CSV/Excel) |
| Tests | pytest — 56 tests |
| Containers | Docker multi-stage + Docker Compose |
| Cloud | AWS ECS Fargate · GCP Cloud Run · Azure Container Apps |
| IaC | Terraform (AWS) |
| CI/CD | GitHub Actions → GHCR |

---

## 🔮 Roadmap

- [x] Business KPI Dashboard
- [x] Advanced SQL Analytics with window functions
- [x] CSV and Excel export
- [x] Price forecasting with confidence bands
- [x] Power BI connector and dashboard previews
- [ ] Email / Slack alerts on anomaly events
- [ ] Backtesting mode — replay historical ticks through the full pipeline
- [ ] Strategy simulation — moving-average crossover signals
- [ ] Grafana dashboard on TimescaleDB continuous aggregates
- [ ] Kubernetes Helm chart

---



<div align="center">

<!--  ╔══════════════════════════════════════════════════════════╗
      ║              STOCHASTIX  —  HERO FOOTER                 ║
      ╚══════════════════════════════════════════════════════════╝  -->

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:7c3aed,50:9333ea,100:c084fc&height=180&section=footer&text=Built%20with%20%E2%9D%A4%EF%B8%8F%20by%20Stochastix&fontSize=22&fontColor=ffffff&fontAlignY=65&animation=twinkling" width="100%"/>

</div>

