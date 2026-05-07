# Qumulo GPU Horizon

Multi-cloud GPU capacity marketplace with automated Qumulo spoke deployment.

## Architecture

```
frontend/                  React + TypeScript + Tailwind + MapLibre
services/
  api-gateway/             Go · OIDC auth · RBAC · reverse proxy
  gpu-chase-monitor/       Python FastAPI · AWS/Azure/GCP adapters · pricing catalog
  provisioning-engine/     Python FastAPI · Cloud Bridge + Spoke Orchestrator
  cost-telemetry/          Python FastAPI · lifecycle rules · ephemeral teardown
infrastructure/terraform/  IaC modules (scaffolded)
```

## Quick start

```bash
docker compose up --build
# UI: http://localhost:3000
# API gateway: http://localhost:8000
# GPU Chase Monitor: http://localhost:8001/docs
# Provisioning Engine: http://localhost:8002/docs
# Cost & Telemetry: http://localhost:8003/docs
```

## Local dev (no Docker)

```bash
# GPU Chase Monitor
cd services/gpu-chase-monitor
pip install -r requirements.txt
PYTHONPATH=. uvicorn src.main:app --port 8001 --reload

# Provisioning Engine
cd services/provisioning-engine
pip install -r requirements.txt
PYTHONPATH=. uvicorn src.main:app --port 8002 --reload

# Cost & Telemetry
cd services/cost-telemetry
pip install -r requirements.txt
PYTHONPATH=. uvicorn src.main:app --port 8003 --reload

# Frontend
cd frontend
npm install && npm run dev
```

## Cloud credentials

Services auto-detect real cloud credentials and fall back to simulation:

| Service | Real mode triggered by |
|---------|------------------------|
| AWS adapter | `AWS_REGION` env var + boto3 installed |
| Azure adapter | `AZURE_SUBSCRIPTION_ID` env var |
| GCP adapter | `GOOGLE_APPLICATION_CREDENTIALS` or `GOOGLE_CLOUD_PROJECT` |

## Auth

The API Gateway passes through unauthenticated in dev (synthetic admin identity).
Set `OIDC_ISSUER` + `OIDC_CLIENT_ID` env vars to wire a real IdP.

## Phases (per architecture doc)

- **Phase 0** — Foundations (current): architecture, scaffolding, cloud adapter stubs, design partners
- **Phase 1** — Standalone MVP: GPU Chase Monitor live, spoke + compute configurator, one HPC orchestrator end-to-end
- **Phase 2** — HPC depth: all three orchestrators, storage-aware placement hints
- **Phase 3** — Nexus integration
