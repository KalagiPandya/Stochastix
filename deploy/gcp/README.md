# ☁️ GCP Deployment Guide — Cloud Run + Cloud SQL

Stochastix PRO maps cleanly onto **Cloud Run** (serverless containers),
**Cloud SQL for PostgreSQL** (with TimescaleDB via the
`pg_partman`/Timescale-compatible extensions on Cloud SQL Enterprise Plus,
or a self-managed TimescaleDB on Compute Engine), and **Memorystore for
Redis** for the streaming backbone.

```
            ┌────────────────────────┐
 Internet ─▶│   Cloud Run service      │  (auto-scaling, HTTPS by default)
            │   stochastix-pro          │
            └──────────┬───────────────┘
                        │  (Serverless VPC connector)
          ┌─────────────┼──────────────────┐
          ▼                                 ▼
 ┌────────────────────┐          ┌──────────────────────┐
 │ Cloud SQL Postgres   │          │ Memorystore Redis      │
 │ (DB_BACKEND=postgres)│          │ (STREAM_BACKEND=redis) │
 └─────────────────────┘          └────────────────────────┘
```

## 1. Build & push the image to Artifact Registry
```bash
PROJECT_ID=$(gcloud config get-value project)
REGION=us-central1

gcloud artifacts repositories create stochastix --repository-format=docker --location=$REGION
gcloud auth configure-docker $REGION-docker.pkg.dev

docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/stochastix/stochastix-pro:latest .
docker push $REGION-docker.pkg.dev/$PROJECT_ID/stochastix/stochastix-pro:latest
```

## 2. Provision Cloud SQL (PostgreSQL/TimescaleDB)
```bash
gcloud sql instances create stochastix-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION

gcloud sql databases create stochastix --instance=stochastix-db
gcloud sql users set-password postgres --instance=stochastix-db --password=ChangeMe123!
```
> For full TimescaleDB hypertable support, either use **Cloud SQL Enterprise
> Plus** (which supports the `timescaledb` extension) or run TimescaleDB on
> a Compute Engine VM / GKE and point `POSTGRES_HOST` at it.

## 3. Provision Memorystore Redis (optional, STREAM_BACKEND=redis)
```bash
gcloud redis instances create stochastix-redis \
  --size=1 --region=$REGION --tier=basic
```

## 4. Store secrets
```bash
echo -n "$(python -c 'import secrets;print(secrets.token_hex(32))')" | \
  gcloud secrets create stochastix-jwt-secret --data-file=-

echo -n "ChangeMe123!" | gcloud secrets create stochastix-db-password --data-file=-
```

## 5. Deploy to Cloud Run
```bash
gcloud run deploy stochastix-pro \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/stochastix/stochastix-pro:latest \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --port=8501 \
  --add-cloudsql-instances=$PROJECT_ID:$REGION:stochastix-db \
  --set-env-vars="DB_BACKEND=postgres,POSTGRES_HOST=/cloudsql/$PROJECT_ID:$REGION:stochastix-db,POSTGRES_DB=stochastix,POSTGRES_USER=postgres,STREAM_BACKEND=redis,REDIS_URL=redis://<memorystore-ip>:6379/0" \
  --set-secrets="POSTGRES_PASSWORD=stochastix-db-password:latest,JWT_SECRET_KEY=stochastix-jwt-secret:latest"
```

## 6. Access
Cloud Run prints a `*.run.app` HTTPS URL — open it directly, TLS is
provisioned automatically.

---

## Alternative: GKE (Kubernetes)
For a Kafka-based pipeline (`STREAM_BACKEND=kafka`), GKE + **Confluent for
GKE** or **Strimzi** (Kafka on Kubernetes) is the typical pattern. A basic
`Deployment` + `Service` + `Ingress` set for GKE mirrors the ECS task
definition in `deploy/aws/terraform/main.tf` — same image, same env vars,
swap `KAFKA_BOOTSTRAP_SERVERS` to the in-cluster Kafka service DNS name
(e.g. `kafka.kafka.svc.cluster.local:9092`).

## Cost-saving tips
- Cloud Run scales to zero — idle demo costs ~$0.
- `db-f1-micro` Cloud SQL + `basic` tier Memorystore are sufficient for a
  portfolio demo.
