# Standalone GrantFlow Modern on Render

## Target and release gates

Existing service: grantflow-modern-staging, Ohio, repository
Alambdasystem/grantflow-modern-standalone, branch feat/render-staging,
Dockerfile.render-staging, context repository root. Public origin:
https://grantflow-modern-staging.onrender.com . Keep the existing service ID
and URL. This code does not modify the original Anthesis installation.

Root render.yaml and render-core.yaml describe the approved core service:
Starter/0.5c-512mb, one instance, a 1 GB disk at /var/data, HTTP /health.
Alambda provides remote AI; no model container is required. The optional
deploy/render-ollama-optional.yaml is a different, more expensive topology and
must not be applied for this deployment.

Last infrastructure inspection on October 26, 2026 found the existing service
on free compute, no attached disk, automatic deployment off. These are actual
Render settings, independent of repository YAML. The exposed connector cannot
upgrade compute or attach a disk. Apply those settings in the existing service
Dashboard, then verify them before deploying this image. Automatic deploys
require a connected Git provider; a public-repository-URL service may require
manual deploy. A successful push is not proof of deployment.

## Startup and database

The supervisor binds Nginx to 0.0.0.0:$PORT (Render supplies PORT) and starts
Next on loopback 3002 and FastAPI on loopback 8001. Process failure terminates
the container. Initial disk ownership setup runs as root, then all app
processes run as UID/GID 10001. /auth/login redirects to /gfm-app/login;
protected APIs use the real backend, not the historical staging 503 wrapper.

Runtime startup verifies the disk mount and write access. It refuses to run
when database, uploads, private documents, screenshots or browser profiles
escape the persistent root. Schema initialization creates all registered
tables, performs reviewed additive migrations idempotently, checks required
columns, and records schema version 2. It fails on unreviewed schema drift.
SQLite foreign keys, WAL and a busy timeout are enabled. No production database
or uploads are included in Git or the image. No sample account is seeded.

The disk persists across deployments/restarts; only paths beneath /var/data
are durable. One disk means one app instance and deployment downtime. Set
environment from .env.example. A fresh, unique >=32-character
GFM_BOOTSTRAP_TOKEN must be stored as a Render secret before first startup.
Do not disable persistent-storage enforcement to make a free service start.

## Secure first login and account recovery

For a migration of existing users/history, use [existing-data migration](EXISTING-DATA-MIGRATION.md)
instead of the fresh-install procedure below. It preserves owner IDs and
compatible existing passwords and closes bootstrap without replacement accounts.

1. Open /auth/login over HTTPS after the authenticated image is live.
2. Retrieve the setup code privately from Render's GFM_BOOTSTRAP_TOKEN.
3. Enter the code, intended email and organization, username wyf_admin, and a
   new password/passphrase of at least 14 characters. Choose the password in
   the browser; do not send or commit it.
4. The first successful setup atomically closes bootstrap. Remove the setup
   token from Render after setup. Restarted instances do not reopen setup.
5. Use Accounts for explicit invitations, password-recovery links, role changes
   and revocation. Links expire after 24 hours and are single-use; deliver them
   privately. The app does not claim to have emailed them automatically.

Authentication uses scrypt password hashes and random opaque sessions stored
only as hashes. Secure HttpOnly host cookies authorize requests; localStorage
contains only a UI hint. Unsafe requests require exact Origin and CSRF token.
Sessions rotate on refresh, expire absolutely after seven days, and are
revoked on logout, recovery or account changes. Roles and account state are
checked server-side. Invalid, expired and replayed sessions are denied.

Original Anthesis supplies both proxy routing and central identity validation
in the original installation. The standalone mode replaces identity with the
provider above; it does not use the original user's password, central session
or email-based account merging. Creating wyf_admin here does not automatically
import the old organization, nine applications or documents. Any private
owner-scoped import requires explicit identity/organization mapping, backup
and validation. Never include original account hashes/tokens or user data in
the repository or image. Production WYF repair remains unapplied.

## AI and integration limits

AI_PROVIDER=alambda, AI_ENABLED=true and
ALAMBDA_CHAT_URL=https://api.alambda.com/api/chat configure remote chat.
A synthetic live POST returned HTTP 200 with the requested answer on October
26, 2026 after an earlier 404. This establishes host connectivity, not Render
egress, model provenance or full in-app integration. Test from Render after
deployment. The remote contract is non-streaming; complete output is delivered
as one chunk. /ready includes recent successful chat readiness and may return
503 before the first successful AI request; /health checks core DB/worker and
remains the platform health check. AI failure preserves existing drafts.

See ALAMBDA-CHAT-CONFIGURATION.md for server-only service-token settings.
Email Safety remains disconnected in standalone mode: user cookies are never
forwarded as central credentials and email safeguards are never bypassed.
Portal automation needs approved sandbox accounts, browser/session/MFA access
and integration configuration. External grant/foundation/donor/payment/email
paths need their own credentials and acceptance; fixture success does not
establish those live integrations. No real submission/email/payment is part
of this release verification.

## Backup, restore and rollback

Use Render Shell/SSH as an authorized operator. Snapshots contain private data:
encrypt and retain them outside Git and the public image.

1. Create /var/data/.maintenance. The supervisor stops frontend, backend and
   workers, then /health returns maintenance=true, ready=false; other requests
   return 503. Confirm this response before copying files.
2. With writers stopped, run:
   `python /opt/grantflow/storage.py backup /var/data /tmp/grantflow-backup.zip --writers-stopped`
3. Copy the archive privately off the instance using authenticated SCP. Verify
   its checksum. An archive in /tmp alone is not a durable backup.
4. Remove /var/data/.maintenance to resume service, then check core health and
   sign-in. The maintenance marker survives restart until explicitly removed.

Restore into a new empty subdirectory on the attached disk while maintenance
is active, e.g. /var/data/restored-release. The restore tool validates archive
paths/checksums/SQLite integrity/foreign keys and refuses existing content:
`python /opt/grantflow/storage.py restore /tmp/grantflow-backup.zip /var/data/restored-release --writers-stopped`
Ensure restored files belong to UID/GID 10001. Set DATABASE_URL and all file
paths to the restored location, keeping GFM_DATA_ROOT=/var/data, then deploy
and verify accounts, application rows and upload download hashes. Keep the
previous data until validation completes; do not overwrite a running database.

Before release, keep a verified database/files backup and the previous image
commit. Rollback code only when compatible with current schema. Render code
rollback does not roll back disk contents or database migrations. Restore a
verified backup separately when necessary. Do not roll back to the historical
placeholder as a substitute for recovering authenticated user data.

## Verification scope

Independent authentication/security regression: 38 tests passed, covering
bootstrap, real password hashing, sessions/rotation/revocation, CSRF, roles,
cross-organization denial, schema idempotence, uploads, central compatibility,
identity repair fixtures and backup validation. Alambda adapter: 8 fixture
tests passed; live synthetic HTTP 200 tested separately.

Local production-image browser acceptance previously passed 8 creation/login/
upload/logout checks, 2 persistence/recreation checks, and 2 real separate-
Ollama AI checks under a 512 MB app limit. These are local results, not proof
of a live Render release. Final rebuilt-image and deployed-service results
must be recorded separately, including actual deployed commit, disk setup,
login, dashboard, create/reopen, upload, invalid session and persistence.

Final local production-image build passed. The rebuilt image passed account,
session, application and upload persistence after recreation (2 checks), real
password sign-in plus actual Alambda inference through the visible app (2
checks; AI request 6.378 seconds), and a quiesced maintenance backup/restore
with archive/SQLite validation. The combined release regression passed 46
tests. All three Blueprint files passed current Render JSON-schema validation.
These do not establish live Render persistence or application readiness.
