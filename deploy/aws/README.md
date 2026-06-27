# ☁️ AWS Deployment Guide

Two supported paths: a quick single-instance **EC2 + Docker** deploy, and a
scalable **ECS Fargate** deploy behind an Application Load Balancer with
RDS (PostgreSQL/TimescaleDB) and MSK (managed Kafka) or ElastiCache (Redis).

---

## Option A — EC2 + Docker (fastest path to a demo URL)

1. **Launch an EC2 instance**
   - AMI: Ubuntu 22.04 LTS, instance type `t3.medium` (2 vCPU / 4 GB) or larger
   - Security group: allow inbound TCP `8501` (Streamlit) and `22` (SSH)

2. **Install Docker**
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-plugin
   sudo usermod -aG docker $USER && newgrp docker
   ```

3. **Deploy**
   ```bash
   git clone <your-repo-url> stochastix && cd stochastix
   cp .env.example .env   # edit secrets, set JWT_SECRET_KEY
   docker compose up -d --build
   ```

4. **Access**: `http://<EC2_PUBLIC_IP>:8501`

5. **(Recommended) Put it behind HTTPS** with an Elastic IP + Nginx/Caddy
   reverse proxy + Let's Encrypt, or place an ALB in front of the instance.

---

## Option B — ECS Fargate (production, auto-scaling)

```
                ┌──────────────────────────┐
   Internet ──▶ │  Application Load Balancer│
                └─────────────┬─────────────┘
                               │
                  ┌────────────▼────────────┐
                  │   ECS Fargate Service     │
                  │   (stochastix container)  │
                  │   desired count: 2-10      │
                  └──┬───────────┬───────────┘
                     │           │
          ┌──────────▼───┐   ┌───▼────────────┐
          │ RDS PostgreSQL │   │ MSK (Kafka) or  │
          │ + TimescaleDB  │   │ ElastiCache     │
          │ (DB_BACKEND=   │   │ (Redis Streams) │
          │  postgres)     │   │ STREAM_BACKEND= │
          └────────────────┘   │  kafka | redis  │
                                └─────────────────┘
```

### Steps

1. **Build & push the image to ECR**
   ```bash
   aws ecr create-repository --repository-name stochastix-pro
   ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
   REGION=us-east-1
   aws ecr get-login-password --region $REGION | docker login --username AWS \
     --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

   docker build -t stochastix-pro .
   docker tag stochastix-pro:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/stochastix-pro:latest
   docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/stochastix-pro:latest
   ```

2. **Provision infrastructure with Terraform**
   ```bash
   cd deploy/aws/terraform
   terraform init
   terraform apply \
     -var="image_url=$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/stochastix-pro:latest" \
     -var="jwt_secret_key=$(python -c 'import secrets;print(secrets.token_hex(32))')"
   ```
   This provisions: VPC, ECS cluster + Fargate service, ALB, RDS for
   PostgreSQL (with the `timescaledb` extension enabled via parameter group),
   ElastiCache Redis (for `STREAM_BACKEND=redis`), Secrets Manager entries
   for DB credentials and `JWT_SECRET_KEY`, and CloudWatch log groups.

3. **Environment variables injected by Terraform into the task definition**:
   - `DB_BACKEND=postgres`, `POSTGRES_HOST=<rds-endpoint>`, etc.
   - `STREAM_BACKEND=redis`, `REDIS_URL=<elasticache-endpoint>`
   - `JWT_SECRET_KEY` from Secrets Manager

4. **Access**: the ALB DNS name output by Terraform (`alb_dns_name`).

### Kafka on AWS (alternative to Redis)
For a higher-throughput data-engineering story, swap ElastiCache for
**Amazon MSK** (managed Kafka). Set `STREAM_BACKEND=kafka` and
`KAFKA_BOOTSTRAP_SERVERS` to the MSK bootstrap brokers. The MSK module is
included but commented out in `terraform/main.tf` — uncomment to enable.

---

## Cost-saving tips
- `t3.medium` EC2 + `db.t3.micro` RDS comfortably runs a demo for a few
  dollars/month if stopped when not in use.
- TimescaleDB compression + retention policies (enabled in
  `pipeline/postgres_db.py`) keep RDS storage costs bounded automatically.
