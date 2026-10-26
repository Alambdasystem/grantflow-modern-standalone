# Render staging and remaining integration work

The `feat/render-staging` branch adds `Dockerfile.render-staging`: the existing Next.js frontend and FastAPI backend behind an Nginx listener. It initializes a fresh SQLite schema at `/data/grantflow-staging.db`. It does not import existing data, accounts, uploads, or model files. Staging workers are disabled and every backend route except `/health` returns 503. The public `/auth/login` page explains that sign-in is pending; it never collects credentials. `/ready` deliberately returns 503 until a connected deployment replaces this scaffold.

Without an attached Render persistent disk, `/data` is ephemeral. This scaffold cannot accept user records and must not be described as a usable or durable grant-management deployment. Attach a paid persistent disk and verify UID 10001 write access before enabling live operations. Startup recreates the empty schema on ephemeral storage; this is not data recovery.

## Prompt for the agent with access to the original system

Investigate `Alambdasystem/grantflow-modern-standalone`, including `feat/separate-host-readiness` and `feat/render-staging`. Preserve the existing original installation. Do not copy production data, credentials, accounts, browser profiles, or uploads into the public repository.

Explain precisely what was packaged: schema and initialization code versus database records, files, models, and central identity. Inspect the actual login flow, stable identity mapping, password/token issuance, refresh, introspection, revocation, tenant ownership, and Email Safety dependencies. The source currently redirects browser login to `/auth/login` and relies on Anthesis; it is not independently authenticated.

Prepare a concrete implementation for a separately deployable GrantFlow instance. Prefer preserving the existing central-auth contract if an approved reachable HTTPS Anthesis origin can be supplied. Provide the non-secret origin, exact login/refresh/identity/revocation/operator paths, required CA/secret-file names, asset paths, redirects, and secure provisioning steps. Do not paste keys into chat or commit them. If complete independence is required, propose and implement a real standalone authentication provider with password hashing, secure session handling, refresh/revocation, rate limits, role/tenant enforcement, and account recovery; do not reuse the lab fixture as production authentication.

Provide idempotent schema initialization and migration instructions, plus an optional separately approved encrypted data-export/import workflow. Provision durable Render storage before user writes. Preserve the reviewed model digest and capacity requirements; configure Ollama and verify loaded-model readiness. Keep AI and provider functions visibly unavailable until verified.

Replace the staging-only wrapper only after validating sign-in, logout, refresh, invalid/expired/revoked tokens, viewer write denial, cross-tenant denial, record/file persistence across restart, and API failure behavior. Include tests, a deployment configuration, required non-secret settings, backup/restore, and rollback steps. Do not change the original production application.
