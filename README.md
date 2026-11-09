# Qumulo GPU Horizon

Multi-cloud GPU capacity marketplace — real-time availability and pricing for AWS, Azure, and GCP GPU instances.

## Running Locally

### Prerequisites

**Docker** — required to run the full stack.

- **Mac (Homebrew):**
  ```bash
  brew install --cask docker
  open /Applications/Docker.app   # wait for the menu bar whale to stop animating
  ```
- **Mac (manual):** download Docker Desktop from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
- **Linux:** follow [docs.docker.com/engine/install](https://docs.docker.com/engine/install/)

Verify Docker is ready:
```bash
docker --version
docker compose version
```

---

### Step-by-step

**1. Clone the repo**
```bash
git clone https://github.com/msperez/qumulogpuhorizon.git
cd qumulogpuhorizon
git checkout claude/qumulo-gpu-horizon-QFak2
```

**2. Create a `.env` file with your AWS credentials**
```bash
cat > .env << 'EOF'
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=ASIA...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...
EOF
```

> Azure pricing loads automatically without credentials.  
> GCP requires `GOOGLE_CLOUD_PROJECT` + `GOOGLE_APPLICATION_CREDENTIALS`.  
> The `.env` file is gitignored — credentials are never committed.

**3. Start the stack**

On Mac (no `sudo` needed):
```bash
# Docker Desktop v4+ (newer)
docker compose build && docker compose up

# If that fails, use the older syntax:
docker-compose build && docker-compose up
```

On Linux:
```bash
sudo -E docker compose build && sudo -E docker compose up
```

> First build takes ~3–5 minutes. Subsequent starts are fast.

**4. Open the app**

| Service | URL |
|---------|-----|
| GPU Map | http://localhost:3000 |
| API docs | http://localhost:8001/docs |

**5. Verify data is loading**
```bash
docker compose logs gpu-chase-monitor 2>&1 | grep "catalog loaded"
# Expected: Initial GPU catalog loaded: 284 SKUs (or similar)
```

**Stop the stack**
```bash
docker compose down
```

---

### AWS SSO users

Run `aws sso login` first, then export the temporary credentials into `.env`:
```bash
aws configure export-credentials --format env-no-export \
  | grep -E "AWS_" > .env
echo "AWS_REGION=us-east-1" >> .env
```

---

### Architecture

```
frontend/              React + TypeScript + Tailwind + MapLibre
services/
  api-gateway/         Go · OIDC auth · reverse proxy
  gpu-chase-monitor/   Python FastAPI · AWS/Azure/GCP adapters
  provisioning-engine/ Python FastAPI · spoke orchestration
  cost-telemetry/      Python FastAPI · lifecycle + teardown
```
