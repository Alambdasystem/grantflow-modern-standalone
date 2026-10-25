# Trial deployment, recovery and rollback (review only)

No target deployment or original-service restart is authorized by this package.
All commands below are for a new host and the separate `grantflow-trial` project.

## Release preparation

1. Build reviewed branch images from this repository with `Dockerfile.backend`
   and `Dockerfile.frontend`. Promote the resulting immutable image digests to a
   private registry or export/load the exact tested images. Record source commit,
   image IDs/digests, configuration checksum and model digest in a release record.
   Do not copy an original database, credential store or browser profile.
2. Provision DNS/private connectivity, TLS and sandbox central services as in
   [ANTHESIS.md](ANTHESIS.md). Review egress firewall rules. Supply secret files
   outside Git with restrictive permissions. Compose file secrets are mounted
   files, not an encrypted secret-management service. Do not put keys in images.
   Verify the backend's UID 10001 can read its mounted key/CA/client-certificate
   files without printing their contents. File-backed Compose secret ownership
   depends on the host; a root-only source file can otherwise cause a deliberate
   503/startup refusal. Keep private keys readable only by the intended service
   identity. Review gateway TLS-key permissions separately. Never fix access by
   making a secret world-readable or disabling TLS verification.
3. Copy `deploy/.env.trial.example` to `deploy/.env.trial`. Replace every placeholder,
   set public origin/CORS to the exact HTTPS browser origin, and use immutable
   backend/frontend image references. The example intentionally cannot start a
   connected application. Required real secret paths/approved DNS are gates.
4. Precreate an empty data volume and initialize its ownership for UID 10001:

   ```sh
   docker volume create grantflow-trial-data
   docker run --rm --user 0 -v grantflow-trial-data:/data --entrypoint sh "$BACKEND_IMAGE" -c 'chown 10001:10001 /data'
   ```

   `BACKEND_IMAGE` here must be the same reviewed image selected in the env file.
   Database startup creates current tables/columns using retained `init_db`.
   Legacy import stays disabled. Required migration code is retained; importing
   production accounts/data is a separate reviewed migration, not automatic startup.

## Topology and model provisioning

Connected local-model topology: TLS gateway -> Next.js -> FastAPI/SQLite/files
and in-process automation/ingestion workers, with private Ollama. Only gateway
TLS is published; API/model ports remain private. Model, data/uploads/documents/
screenshots/browser profile persist in named volumes. There is no invented Redis
or Celery dependency: the copied implementation uses its existing worker path.

Use Compose from `deploy/` with `--env-file .env.trial -f compose.yaml` on **every**
command. For the local model also use `--profile local-model`. Example after all
gates are approved:

```sh
docker compose --env-file .env.trial -f compose.yaml --profile local-model config --quiet
docker compose --env-file .env.trial -f compose.yaml --profile local-model up -d
```

The model service has no internet access. Provision its volume in a separate,
controlled download step using the pinned Ollama image and approved registry
egress. Pull `llama3.2:latest`, then inspect `/api/tags` and require digest
`a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`.
The model is 3.2B Q4_K_M, artifact size 2,019,393,189 bytes; context remains 4096
and parallelism 1. The tag alone is not an immutable model approval. If it no
longer resolves to that digest, use the protected approved model-volume artifact
or stop for review. Do not silently substitute another model/provider.

Alternative: run the **same model** on a separate managed host. Omit the local
profile, set `OLLAMA_URL=https://<approved-model-host>`, add
`-f compose.remote-model.yaml`, supply `MODEL_CA_FILE`, `MODEL_CLIENT_CERT_FILE`,
`MODEL_CLIENT_KEY_FILE` and set backend paths `AI_CA_BUNDLE=/run/secrets/model_ca`,
`AI_CLIENT_CERT_FILE=/run/secrets/model_client_cert`,
`AI_CLIENT_KEY_FILE=/run/secrets/model_client_key` in `.env.trial`.
The remote operator must configure mutual TLS, access restrictions, capacity,
the identical model digest and readiness. No remote endpoint was provisioned or
certified here. This changes placement/latency/operations, not model capability.

## Startup and readiness

`/health` checks database and automation-worker liveness; Ollama health only means
its process responds. Explicitly warm and check readiness before accepting users:

```sh
docker compose --env-file .env.trial -f compose.yaml --profile local-model --profile ops run --rm --no-deps warm-model
curl --fail --cacert trial-ca.pem https://<trial-origin>/ready
```

`/ready` also requires the exact model present and loaded in `/api/ps`. It returns
503 on missing/unloaded/wrong-digest/unreachable model. Polling never loads one.
The idle model can unload after its keep-alive; re-warm before opening AI traffic.
The existing inference path loads it explicitly and retains fail-closed errors.
Loading and generation have separate 180-second deadlines; gateway/Next proxy
allows 420 seconds. Prior real cold saved generations took 101–149 seconds;
allocate startup grace accordingly. Do not interpret green Compose containers
as model readiness or central-integration acceptance. Docker restart policies do
not automatically restart an unhealthy-but-running process; operators must alert
on health/readiness/OOM and investigate rather than restart-loop away evidence.

## Consistent backup and restore

Quiesce gateway, backend and **all** writers/remote workers; no warm/ops job may
write during backup. The offline tool cannot enforce external quiescence. It uses
SQLite Backup API, integrity check, complete data-tree copy and per-file SHA-256.
Protect backups as private records; encrypt/store off-host under operator policy.
Do not put them in Git. Keys/certificates and model volumes are separate recovery
assets and are not bundled in a data backup.

```sh
docker compose --env-file .env.trial -f compose.yaml stop gateway backend
docker compose --env-file .env.trial -f compose.yaml --profile ops run --rm --no-deps storage backup /data /backups/release-before-change.zip --writers-stopped
docker compose --env-file .env.trial -f compose.yaml start backend gateway
```

Retain the printed archive checksum with release provenance. For a restore drill,
select a **new empty** `DATA_VOLUME` (for example `grantflow-trial-restore-001`) in
a private copied env file. Stop the trial services and remove only their stopped
containers (`down`, **never `down -v`**); then run with the selected env file:

```sh
docker compose --env-file .env.restore -f compose.yaml --profile ops run --rm --no-deps storage restore /backups/release-before-change.zip /data --writers-stopped
```

The tool refuses nonempty targets, duplicate/unsafe archive paths, bad checksums,
symlinks and invalid database/foreign keys. Restore as root, then set all restored
data ownership to UID/GID 10001 with a one-off reviewed image/container. Recreate
services against the selected volume, warm the model, verify `/ready`, synthetic
tenant/role denials, saved records and file hashes. Keep the previous volume intact.
Synthetic roundtrip/corruption/overwrite tests are included. A full target-host
disaster-recovery drill remains required; no real backup was restored here.

## Rollback

Stop trial traffic/writers; capture a failure snapshot before rollback. Select the
previous immutable images and matching **new restored** data volume/configuration.
Do not overlay an older database onto newer files or merge writes implicitly.
Recreate only this project, warm/verify readiness and repeat role/tenant/file
checks before reopening. Preserve the failed volume for investigation. Recovery
point is the selected backup; review later writes explicitly. Never run these
commands against the original installation or apply the WYF proposal as rollback.

Source archives may be created with `git archive` from the reviewed commit; they
contain tracked sanitized source only. They exclude runtime volumes, model blobs,
credentials and private audit evidence. This is a source release, not a data migration.
