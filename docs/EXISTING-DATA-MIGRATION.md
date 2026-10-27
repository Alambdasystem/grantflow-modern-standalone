# Existing Modern data migration

This is an offline snapshot conversion, not a fresh installation. Private
source databases, central credential snapshots, manifests, conversion reports,
backup archives and uploaded files stay outside Git and Docker build context.
The existing Render service and /var/data disk are reused.

## Authoritative source and identity rules

Verify the running backend's working directory and effective path settings.
Open SQLite read-only and use SQLite's online backup API; do not copy a live
main database file while ignoring WAL. Snapshot the central user store through
a stable read, and record the UTC cutoff and file digests privately. Copy all
configured upload/document/screenshot assets and every explicit document-file
reference, including references outside the application tree. Validate sizes
and SHA-256 before and after copying. Do not enumerate unrelated private files.

Use Modern's users primary keys and existing stable identities. Null identities
receive a deterministic namespace derived from the source tag and user ID.
auth_migrated_accounts stores the explicit mapping and access constraints.
Only exact stable central IDs select central credentials; email and username
matching never links accounts. A central login alias is added only if it does
not collide with an existing username. Separate identities stay separate.

Preserve user roles/organizations and application owner IDs. Central scope,
approval, activation and role ceilings remain restrictions on mapped accounts;
importing a row does not itself grant access. Local supported credentials are
retained for legacy Modern accounts without a stable central link. New runtime
sessions are native GrantFlow opaque sessions, not Anthesis tokens.

Bounded bcrypt and Werkzeug PBKDF2/scrypt verifiers support inspected source
formats. After successful verification, rehash to the current scrypt format.
Do not infer, invent or export passwords. Unsalted SHA hashes, plaintext and
unknown schemes require explicit administrator-issued recovery, preserving the
same user ID, ownership and role. Publish only the private account-specific
recovery report to the authorized operator, not the public repository.

The first-administrator bootstrap closes atomically as part of conversion.
Existing users see normal sign-in. An empty replacement account is not created.

## Rehearsal

1. Keep protected, immutable source snapshots. Copy Modern SQLite to an isolated
   prepared-data/grantflow.db. Keep central credentials outside prepared-data;
   the full Anthesis identity file must not be shipped to Render.
2. Copy assets to prepared-data/uploads, screenshots and private_documents.
   Build a private file plan with files (relative path, bytes, SHA-256) and
   cell_changes (table, id, column, before, after). Destination references use
   /var/data. Required path transformations are allowlisted in the converter.
   The converter also normalizes historical Windows screenshot references,
   including repeated separators and absolute parent-directory components,
   against the exact verified asset manifest. Ambiguous matches, bare filenames,
   unknown assets and relative traversal fail closed; never substitute by name.
3. In the release image, with networking disabled, set AUTH_MODE=standalone,
   DATABASE_URL to the explicit isolated database and a matching public origin/
   CORS. Run /opt/grantflow/import_existing.py with --database, --central,
   --plan, --source-tag, --cutoff and --private-report. The script checks that
   initialization and conversion use the same database. Never target the
   original installation.
4. Compare every original row/cell against the candidate. Only credential
   selection, journaled identity/path/reference changes and paused pending
   jobs may differ. Preserve all original table counts and primary keys.
   Require SQLite integrity and foreign_key_check to pass. Any new unreviewed
   defect blocks conversion.
5. The converter handles only explicitly reviewed nullable missing donation
   references: retain the donation row, detach its absent parent and record the
   original reference in migration_conversion_journal for review. Do not invent
   missing business records. Other FK defects fail closed.
6. Verify historical drafts/notes, owner-filtered reads and document download
   hashes. Keep synthetic password-login tests separate from permission tests
   using a rehearsal-only server session. Never claim an existing user's real
   password was tested when it was not supplied.

An older, separately running GrantFlow database is not automatically merged
into Modern based on matching names. Preserve its protected snapshot separately
and reconcile its records/ownership explicitly if it is included in a future
active-data import. Modern's existing history remains authoritative here.

## Prevent external replay

Imported queued/running/awaiting-approval jobs become paused with their original
state in the conversion journal. Completed/failed history is retained. A durable
migration_safety hold blocks external orchestration, provider login and Workspace
background entry points and scheduling, including after restart. Local workers
can remain healthy and process newly authorized document ingestion. AI still
uses the server-side Alambda adapter without browser credentials.

Do not release the hold until each imported pending job, policy, portal session,
credential and destination integration has been reviewed. Recovery/restart must
not automatically revive imported jobs. Email Safety remains disconnected and
email actions remain unavailable; it is not silently replaced with an unsafe
sender.

## Private transfer and installation

Use an operator-authenticated SSH/SCP channel. Verify Render's published regional
SSH host-key fingerprint. Register a temporary public key if necessary; the
private key stays local. Remove the temporary key after verification. No migration
upload, arbitrary execution or authentication-bypass endpoint is added to HTTP.

1. Verify the destination's live commit, attached disk, free capacity and data
   counts over SSH. If destination records exist, keep them and stop for an
   explicit collision/remapping plan. Do not overwrite or email-merge them.
2. Enter maintenance with /var/data/.maintenance and wait for HTTP /health to
   report maintenance=true. This stops every app/worker writer.
3. Use storage.py backup to create a consistent destination archive outside
   /var/data, transfer it privately off-host and verify its checksum. Preserve
   a protected source snapshot as well. Never rely solely on /tmp retention.
4. Use storage.py backup on the prepared candidate to create a checksummed
   private archive. Transfer to the existing service's /tmp using SCP.
5. Run /opt/grantflow/install_existing.py ARCHIVE --sha256 DIGEST. It requires
   the approved mounted disk and quiesced maintenance response, refuses existing
   destination business records and file collisions, validates the archive,
   bootstrap closure and job hold, and retains the prior destination database
   and archive under private-migration. It leaves maintenance active.
6. Verify counts, relationships, asset hashes and identity mappings directly on
   the disk before removing the maintenance marker. Then verify normal login,
   role/organization boundaries, historical details, downloads, worker health
   and Alambda with synthetic content. Redeploy and repeat persistence checks.

Rollback while maintenance is active using the verified destination-before
archive/database and a compatible code revision. Do not treat a code rollback
as restoration of disk contents. Preserve both states until validation finishes.

## Cutoff and completion

The original remains unchanged and may remain writable. Compare source row
digests and asset/credential-store digests against the snapshot before and after
the destination import. Record all post-cutoff deltas and reconcile them before
claiming a complete cutover. A snapshot migration is not automatic ongoing sync.
An unavailable SSH key, unresolved ownership collision, source drift, unsupported
credential or disconnected integration must remain an explicit gate.
