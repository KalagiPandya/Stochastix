# ☁️ Azure Deployment Guide — Container Apps + Azure Database for PostgreSQL

```
            ┌─────────────────────────────┐
 Internet ─▶│  Azure Container Apps          │  (auto-scaling, HTTPS ingress)
            │  stochastix-pro                 │
            └───────────────┬─────────────────┘
                              │ (VNet integration)
            ┌─────────────────┼──────────────────────┐
            ▼                                          ▼
 ┌───────────────────────────────┐        ┌──────────────────────────┐
 │ Azure Database for PostgreSQL    │        │ Azure Cache for Redis       │
 │ Flexible Server                  │        │ (STREAM_BACKEND=redis)      │
 │ + TimescaleDB extension           │        └──────────────────────────┘
 │ (DB_BACKEND=postgres)             │
 └───────────────────────────────┘
```

## 1. Build & push to Azure Container Registry
```bash
RG=stochastix-rg
LOCATION=eastus

az group create --name $RG --location $LOCATION
az acr create --resource-group $RG --name stochastixacr --sku Basic
az acr login --name stochastixacr

docker build -t stochastixacr.azurecr.io/stochastix-pro:latest .
docker push stochastixacr.azurecr.io/stochastix-pro:latest
```

## 2. Provision Azure Database for PostgreSQL Flexible Server
```bash
az postgres flexible-server create \
  --resource-group $RG \
  --name stochastix-db \
  --location $LOCATION \
  --admin-user stochastix \
  --admin-password "ChangeMe123!" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --version 15

# Enable the TimescaleDB extension (Azure allowlists it via server parameters)
az postgres flexible-server parameter set \
  --resource-group $RG --server-name stochastix-db \
  --name azure.extensions --value timescaledb

az postgres flexible-server db create \
  --resource-group $RG --server-name stochastix-db --database-name stochastix
```

## 3. Provision Azure Cache for Redis (optional, STREAM_BACKEND=redis)
```bash
az redis create --resource-group $RG --name stochastix-redis \
  --location $LOCATION --sku Basic --vm-size c0
```

## 4. Store secrets in Key Vault
```bash
az keyvault create --resource-group $RG --name stochastix-kv --location $LOCATION

az keyvault secret set --vault-name stochastix-kv --name jwt-secret-key \
  --value "$(python -c 'import secrets;print(secrets.token_hex(32))')"

az keyvault secret set --vault-name stochastix-kv --name postgres-password \
  --value "ChangeMe123!"
```

## 5. Deploy to Azure Container Apps
```bash
az containerapp env create --name stochastix-env --resource-group $RG --location $LOCATION

az containerapp create \
  --name stochastix-pro \
  --resource-group $RG \
  --environment stochastix-env \
  --image stochastixacr.azurecr.io/stochastix-pro:latest \
  --target-port 8501 \
  --ingress external \
  --registry-server stochastixacr.azurecr.io \
  --env-vars \
    DB_BACKEND=postgres \
    POSTGRES_HOST=stochastix-db.postgres.database.azure.com \
    POSTGRES_DB=stochastix \
    POSTGRES_USER=stochastix \
    STREAM_BACKEND=redis \
    REDIS_URL=redis://stochastix-redis.redis.cache.windows.net:6380/0 \
  --secrets \
    postgres-password=keyvaultref:https://stochastix-kv.vault.azure.net/secrets/postgres-password,identityref:system \
    jwt-secret=keyvaultref:https://stochastix-kv.vault.azure.net/secrets/jwt-secret-key,identityref:system \
  --secret-env-vars \
    POSTGRES_PASSWORD=postgres-password \
    JWT_SECRET_KEY=jwt-secret
```

## 6. Access
Azure prints a `*.azurecontainerapps.io` HTTPS URL — TLS is automatic.

---

## Alternative: Azure VM + Docker Compose (quickest demo)
```bash
az vm create --resource-group $RG --name stochastix-vm \
  --image Ubuntu2204 --size Standard_B2s --generate-ssh-keys \
  --public-ip-sku Standard

az vm open-port --resource-group $RG --name stochastix-vm --port 8501

ssh azureuser@<vm-ip> \
  "sudo apt update && sudo apt install -y docker.io docker-compose-plugin \
   && git clone <your-repo-url> stochastix && cd stochastix \
   && cp .env.example .env && docker compose up -d --build"
```

## Cost-saving tips
- Container Apps scales to zero on the Consumption plan.
- `Standard_B1ms` / Basic-tier Redis are sufficient for demo workloads.
