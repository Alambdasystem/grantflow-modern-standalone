# GrantFlow Modern standalone

Independent source-only repository for the isolated Modern application. It has no inherited project history, production database, real account store, uploads, credentials, model cache or private audit evidence. The original installation is outside this repository and is not a build dependency.

The default Compose project is a **synthetic local lab**, published only at `http://127.0.0.1:5100/auth/login`. Its identity fixture is deliberately not production authentication. No connected deployment or original traffic cutover is authorized by these files.

## Build and reproduce

Baseline `4054e69` was independently cloned and both images built before readiness
changes: [build record](docs/BASELINE-BUILD.md). Separate-host review instructions,
resource findings and open gates are in [trial readiness](docs/trial/READINESS.md),
[Anthesis contracts](docs/trial/ANTHESIS.md) and [operations](docs/trial/OPERATIONS.md).
The trial package does not authorize deployment or establish full functional parity.
The [source file manifest](docs/FILE-MANIFEST.txt) lists every published path;
runtime data, secrets, models and private evidence are deliberately excluded.

Requires Docker with Linux containers and Compose. Package/browser/font/model downloads require build/provisioning internet access. All build COPY inputs are relative to this repository. No host Python/Node environment from the original is used.

```sh
docker compose config --quiet
docker compose build
docker compose -f compose.yaml -f compose.ai-provision.yaml up -d ollama
docker compose exec -T ollama ollama pull llama3.2:latest
docker compose up -d --force-recreate ollama
docker compose up -d --wait --wait-timeout 180
mkdir -p evidence/parity
docker compose exec -T backend python /lab/seed_parity.py > evidence/parity/seed.json
docker build -f Dockerfile.verify -t grantflow-lab-tests:local .
docker compose --profile verify run --rm tests --current-only
docker compose --profile verify run --rm frontend-tests
```

Model provisioning temporarily enables model-download egress only. Base Compose recreates Ollama on its internal runtime network. A cold first AI request took 101–149 seconds in the preceding audit; container health alone is not proof of a loaded model. The five-container 2,048 MiB allocation failed with a model OOM. Runtime memory/real-service decisions remain gates.

`docker compose down` retains the data/model volumes. Do not add `-v` when retaining data. The data volume contains SQLite, private uploaded files, screenshots and the lab browser profile; the model volume is separate.

## System entry points

| Area | Files |
|---|---|
| Frontend and routes | `source/frontend/app/layout.tsx`, `app/**/page.tsx`, `components/layout/Sidebar.tsx` |
| API and ownership | `source/backend/main.py`, `routers/*.py`, `auth/jwt_handler.py`, `auth/ownership.py` |
| Database and schema | `source/backend/db/database.py`, `models/models.py`, `startup_seed.py` additive schema helpers |
| Workers and agents | `source/automation/orchestrator.py`, `agents/*.py`, backend `services/job_queue.py`, `document_ingestion.py` |
| Separate extraction worker | `source/scripts/ingestion_worker.py` |
| Required/operator migrations | `source/migration/adapter.py`, `identity_migration.py`, `reviewed_identity_link.py` |
| Gateway and packaging | `lab/nginx.conf`, `compose*.yaml`, `Dockerfile.*`, `requirements*.txt` |
| Synthetic fixtures/tests | `lab/identity_fixture.py`, `seed_parity.py`, backend/frontend tests |

The historical parent Compose, host port-killing launcher and production-targeted inspection/seed scripts are intentionally excluded. Root Compose replaces their launch function. Legacy imports stay disabled; legacy source paths require explicit operator configuration pointing to protected copies. No implicit parent application/account store is imported.

## Acceptance and boundaries

The preceding local audit recorded 44 groups: 35 PASS, one FAIL (the 2 GB allocation), eight BLOCKED, zero NOT TESTED. The original 43 groups plus the explicit resource test explain the increase. The sanitized [matrix](docs/audit/feature-parity-matrix.csv) distinguishes fixtures, actual local execution and real public-provider reads. Private original evidence is retained outside Git. Documentation images are newly captured synthetic-lab views.

Real authentication and Email Safety still depend on Anthesis. Local credential sign-in remains disabled; bypassing the proxy does not bypass identity validation. The synthetic identity repair uses invented users/organizations/nine applications and is not a production repair command.

Base/model image identities and environment configuration will be pinned and validated on `feat/separate-host-readiness`. Packaging success is not full parity or connected-trial acceptance.
