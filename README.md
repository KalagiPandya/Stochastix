# Stochastix 

Real-time financial analytics platform. Streams live BTC/ETH/SOL price data from Binance, detects anomalies with ML models, and presents results across 12 Streamlit dashboard pages.

---

## What it does

- Ingests live tick data via Binance WebSocket
- Stores ticks in DuckDB (dev) or PostgreSQL + TimescaleDB (prod)
- Publishes events to Apache Kafka or Redis Streams
- Detects anomalies using Isolation Forest, Prophet, and LSTM Autoencoder (majority-vote ensemble)
- Runs advanced SQL analytics with window functions, CTEs, and rankings
- Shows business KPI dashboards, price forecasts, and export reports
- Connects to Power BI via CSV/Excel data export
- Secures pages with JWT auth and 3-tier RBAC

---

## Quick Start

```bash
git clone https://github.com/<you>/Stochastix.git
cd Stochastix

pip install -r requirements-core.txt   # lean install, no Prophet/LSTM
streamlit run app.py                   # http://localhost:8501
```

Full install (all ML models):
```bash
pip install -r requirements.txt
```

Zero-config mode runs entirely on DuckDB — no broker or database setup needed. All enterprise features activate via `.env`.

---

## Docker

```bash
# Minimal — DuckDB only
docker compose up --build

# Full stack — TimescaleDB + Redis
docker compose --profile postgres --profile redis up --build

# With Kafka
docker compose --profile postgres --profile kafka up --build
```

---

## Dashboard Pages

| Page | Role | Description |
|---|---|---|
| Home | viewer | Live ticker, SMA/EMA overlay, anomaly alert banner |
| Volatility | viewer | Bollinger Bands, rolling volatility, regime classifier |
| Anomaly | viewer | Z-score series, threshold bands, anomaly event log |
| Comparison | viewer | Normalised % performance, OHLC candlestick, metrics table |
| Data Explorer | viewer | Browse and export raw ticks, metrics, candles |
| ML Anomaly | analyst | Isolation Forest, Prophet, LSTM scores and ensemble vote |
| Login | public | Sign in, register, RBAC capability matrix |
| KPI Dashboard | viewer | Executive KPI cards, anomaly rate gauge, price distribution |
| SQL Analytics | viewer | 6 advanced queries: window functions, rankings, moving averages |
| Export Reports | viewer | Download market data and analytics as CSV or Excel |
| Forecasting | viewer | Linear regression + EMA forecast, confidence bands |
| Power BI Connector | viewer | Dashboard previews and Power BI-ready data export pack |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Dashboard | Streamlit + Plotly |
| WebSocket | Binance `@trade` stream |
| Streaming | Apache Kafka / Redis Streams |
| Database | DuckDB (dev), PostgreSQL + TimescaleDB (prod) |
| Analytics | NumPy, Pandas |
| ML | scikit-learn, Prophet, PyTorch (LSTM) |
| Auth | PyJWT, bcrypt |
| Reporting | openpyxl, Power BI (CSV/Excel) |
| Testing | pytest (56 tests) |
| Containers | Docker multi-stage, Docker Compose |
| Cloud | AWS ECS Fargate, GCP Cloud Run, Azure Container Apps |
| IaC | Terraform (AWS) |
| CI/CD | GitHub Actions |

---

## Project Structure

```
Stochastix/
├── app.py                          # Home dashboard (entry point)
├── pages/
│   ├── 1_Volatility.py             # Bollinger Bands, volatility regimes
│   ├── 2_Anomaly.py                # Z-score anomaly detection
│   ├── 3_Comparison.py             # Multi-asset OHLC comparison
│   ├── 4_Data_Explorer.py          # Browse and export raw data
│   ├── 5_Login.py                  # Auth, register, RBAC matrix
│   ├── 6_ML_Anomaly.py             # Isolation Forest, Prophet, LSTM  [analyst+]
│   ├── 7_KPI_Dashboard.py          # Business KPI metrics, anomaly gauge
│   ├── 8_SQL_Analytics.py          # Window functions, CTEs, rankings
│   ├── 9_Export_Reports.py         # CSV and Excel export
│   ├── 10_Forecasting.py           # Linear regression + EMA forecasts
│   └── 11_PowerBI_Connector.py     # Power BI dashboards and data export
├── services/
│   ├── analytics.py                # SMA, EMA, volatility, Z-score, ROC
│   ├── stream.py                   # Binance WebSocket ingestion + buffer
│   ├── streaming_backbone.py       # Kafka / Redis Streams publisher
│   └── ml_anomaly.py               # ML ensemble (IF, Prophet, LSTM)
├── pipeline/
│   ├── __init__.py                 # DB_BACKEND switcher
│   ├── database.py                 # DuckDB backend
│   └── postgres_db.py              # PostgreSQL + TimescaleDB backend
├── auth/
│   └── security.py                 # JWT, bcrypt, RBAC, role guard
├── deploy/
│   ├── aws/                        # ECS Fargate + Terraform
│   ├── gcp/                        # Cloud Run
│   └── azure/                      # Container Apps
├── tests/                          # 56 pytest tests
├── .github/workflows/ci-cd.yml     # lint → test → build → publish → deploy
├── Dockerfile
├── docker-compose.yml
├── requirements.txt                # Full (all ML deps)
├── requirements-core.txt           # Lean (sklearn only)
└── .env.example
```

---

## Configuration

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

**Auth**
```bash
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
DEFAULT_ADMIN_USER=admin
DEFAULT_ADMIN_PASSWORD=change-me
```

**RBAC roles**

| Role | Access |
|---|---|
| viewer | Read-only dashboards |
| analyst | + ML Anomaly, data export |
| admin | + user management, full config |

---

## Cloud Deployment

All three clouds use the same Docker image and env vars.

| Cloud | Service | IaC |
|---|---|---|
| AWS | ECS Fargate + ALB + RDS + ElastiCache | Terraform |
| GCP | Cloud Run + Cloud SQL + Memorystore | CLI |
| Azure | Container Apps + Azure DB + Azure Cache | CLI |

```bash
# AWS
cd deploy/aws/terraform
terraform init && terraform apply \
  -var="image_url=<ecr-uri>" \
  -var="jwt_secret_key=$(python -c 'import secrets;print(secrets.token_hex(32))')"
```

Full guides: [AWS](deploy/aws/README.md) · [GCP](deploy/gcp/README.md) · [Azure](deploy/azure/README.md)

---

## Tests

```bash
pytest tests/ -v
```

```
tests/test_analytics.py              30 passed
tests/test_auth.py                    9 passed
tests/test_ml_anomaly.py             12 passed
tests/test_streaming_backbone.py      5 passed
                              total: 56 passed
```

---

## Power BI Setup

1. Run the app and go to the **Power BI Connector** page
2. Download the **Full Power BI Pack (.xlsx)** — contains three sheets: `Fact_Prices`, `Dim_Analytics`, `Summary_KPI`
3. In Power BI Desktop: **Get Data → Excel Workbook** → select all three sheets → Load
4. Relate tables on `symbol` and `ts` in Model view

Useful DAX measures:
```
Avg Price     = AVERAGE(Fact_Prices[price])
Anomaly Rate  = DIVIDE(COUNTROWS(FILTER(Dim_Analytics, Dim_Analytics[anomaly] = TRUE())), COUNTROWS(Dim_Analytics))
Price Range   = MAX(Fact_Prices[price]) - MIN(Fact_Prices[price])
Current Price = LASTNONBLANK(Fact_Prices[price], 1)
```

---

## Resume Bullet

```
Built Stochastix PRO, a real-time financial analytics platform in Python: ingests
live BTC/ETH/SOL ticks via Binance WebSocket, streams events through Apache Kafka /
Redis Streams, and persists to PostgreSQL + TimescaleDB (hypertables, compression,
retention) with DuckDB fallback. Detects anomalies using Isolation Forest, Prophet,
and LSTM Autoencoder (majority-vote ensemble) alongside Z-score baselines. Advanced
SQL analytics with window functions (RANK, LAG, LEAD, NTILE, PERCENT_RANK). Business
KPI dashboards, price forecasting with confidence bands, CSV/Excel reporting, and a
Power BI connector. JWT + bcrypt RBAC (admin/analyst/viewer). 12-page Streamlit
dashboard, multi-stage Docker image, Terraform deploy to AWS ECS Fargate / GCP Cloud
Run / Azure Container Apps. GitHub Actions CI/CD, 56-test pytest suite.

Skills: Python · SQL · Power BI · Streamlit · PostgreSQL · Docker · ML · Analytics
```

---

## Roadmap

- [x] Business KPI Dashboard
- [x] Advanced SQL Analytics with window functions
- [x] CSV and Excel export
- [x] Price forecasting with confidence bands
- [x] Power BI connector and dashboard previews
- [ ] Email / Slack alerts on anomaly events
- [ ] Backtesting mode — replay historical data
- [ ] Strategy simulation — moving-average crossover signals
- [ ] Grafana dashboard on TimescaleDB continuous aggregates
- [ ] Kubernetes Helm chart
