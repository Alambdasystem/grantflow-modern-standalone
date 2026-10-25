# Separate-host trial readiness

Updated October 25, 2026. Review package only; no target deployment, production
repair, original-account change or original-service restart occurred.

The private repository is
https://github.com/Alambdasystem/grantflow-modern-standalone . Work is on
`feat/separate-host-readiness`; independent root baseline/main is `4054e69`.
The clean remote clone passed both baseline builds **before** readiness edits:
[baseline evidence](../BASELINE-BUILD.md). Public package downloads were used;
no original installation, account store, environment file or database was a build input.

## What changed

- Explicit, allowlisted HTTPS central identity/revocation/platform/operator URLs;
  mounted service-key file and CA; trial rejects insecure configurations and local
  credential seeding. Raw TLS failures now produce a retryable identity outage.
  Existing identity validation, central roles, stable ownership and tenant gates remain.
- Separate Email Safety host support without weakening its dual-admin/read-only contract.
- Remote model transport with verified CA and client certificates; same model/context.
- `/ready` checks model presence, exact digest and loaded state as well as DB/worker
  liveness. Explicit bounded warmup; health alone no longer implies AI readiness.
- Separate trial Compose/TLS configuration, persistent storage, offline backup/restore
  tool, and rollback runbook. No synthetic identity fixture in connected trial.
- Python/Node base image digests and trial Ollama/Nginx image digests pinned;
  Python transitive constraints and npm lock applied. OS/browser/font downloads
  remain external build inputs: this is not a claim of bit-identical rebuilds.
  Promote tested immutable release images and record provenance.

## Resource decision and readiness

The previous 2,048 MiB allocation failed: the model's 1,184 MiB hard cap produced
an OOM and a 503 during cold AI; concurrent CRUD, extraction and files passed.
That FAIL remains visible. It does not prove all conceivable 2 GB allocations
impossible, and it is **not an actual 2 GB WSL test**.

The candidate lab allocation is 5,824 MiB: model 4,096; backend 1,024;
frontend 512; fixture identity 128; gateway 64, swap disabled. The first cold run
passed startup, three concurrent saved workflows with viewer denial, upload/
worker extraction/hash-matching download, saved real-model draft and existing
record recovery. Cold request took 161.766 seconds; sampled aggregate peak was
3,427,622,912 bytes; model cgroup peak 3,153,264,640 bytes. No memory-limit events,
OOMs or container restarts occurred. See [measured resources](resource-measurements.json)
for the completed runs and exact scope.

| Cold run | Container startup | Saved AI request | Sampled aggregate peak | Model cgroup peak | Result |
|---|---:|---:|---:|---:|---|
| Candidate 1 | 29.594 s | 161.766 s | 3,427,622,912 B | 3,153,264,640 B | PASS |
| Candidate 2, readiness images | 30.329 s | 88.969 s | 3,683,676,160 B | 3,334,451,200 B | PASS |

Both runs had zero OOM/limit events and zero container restarts. In run 2,
`/ready` was 503 with healthy core/unloaded model, then 200 after real inference;
prior saved notes and prior uploaded-file hash survived container recreation.
Concurrent core requests completed in 0.844–1.250 seconds; worker extraction and
download took 1.828–2.704 seconds for the synthetic 190,037-byte text fixture.
Application-wide sampled peak was about 3.43 GiB in run 2. Cgroup component peaks
are noncoincident and must not be confused with a sampled simultaneous total.

Keep the approved 3.2B Q4_K_M model, 4096 context, single inference parallelism.
Use a 4 GiB model allowance for a bounded trial, **not** the failed 1,184 MiB cap.
An 8 GiB trial host is a planning target with OS/daemon headroom; it is an inference
from this small workload, not a measured universal minimum or sustained SLO.
Builds were kept outside the capacity measurement. Larger documents/OCR, more
concurrency and the actual target hardware still require acceptance/load testing.
The Docker VM exposed 12 CPUs and 8,280,391,680 bytes of RAM; neither WSL nor the
original services were restarted/capped. A slower target can exceed the current
AI deadlines even with enough memory and must be measured before admission.

| Placement | Application container allocations | Evidence and tradeoff |
|---|---|---|
| Model beside connected GFM | 5,696 MiB (no lab identity fixture) | Local-model workload measured in the synthetic lab; no WAN latency. Host overhead is additional. |
| Same model on a separate secured host | GFM 1,600 MiB; model 4,096 MiB plus its TLS gateway/OS | Derived split from the same allocation and separate component telemetry, **not an executed two-host capacity or latency test**. Requires mTLS, remote availability and target load test; no change in model capability. |

Existing cold generation evidence was 101–149 seconds; the new concurrent run
took longer. Load and inference deadlines remain separately 180 seconds, with
420-second proxy timeout. Avoid a short orchestrator startup deadline. A cold
model must be explicitly warmed; readiness returns 503 until loaded. Model idle
unload can make readiness unavailable again without a crashed container.

## Matrix accounting and remaining gates

The [complete matrix](../audit/feature-parity-matrix.csv) retains **44 groups:
35 PASS, 1 FAIL, 8 BLOCKED, 0 NOT TESTED**. The original inventory contained 43;
the explicit 2 GB resource acceptance was added as group 44. Readiness subchecks
and a larger-budget candidate do not silently add groups or erase that FAIL.
PASS remains limited to the tested feature scope, not every external provider.

| Group still BLOCKED | What can be verified here | Exact closure requirement |
|---|---|---|
| Real Anthesis credentials, refresh, account lifecycle | Delegation/role/revocation fixtures, TLS transport, configuration denials | Actual sandbox HTTPS/DNS/CA/service key; synthetic writer/viewer/admin identities; browser login/refresh, disable/approval/expiry/app denial and global-revoke acceptance on actual host. |
| External discovery and enrichment | Real public read adapters and synthetic persistence/component tests | Approved restricted runtime egress plus actual discovery -> saved deduplication -> enrichment acceptance in disposable DB on intended topology. Public search alone is insufficient. |
| Full package requirements and bulk scans | Public opportunity resolution and requirements fixtures | Sandbox portal/session, known package/opportunity IDs and expected mandatory forms/attachments; individual and bulk saved-result validation. |
| Google Drive / Graph pickup | OAuth/download/redirect/retry fixtures; safe runner retained | Read-only sandbox credentials, selected synthetic folders/drive/site IDs, expected file hashes and approved egress. No production folder import. |
| Portal login / Login.gov / MFA / session reuse | Real Chromium agents against synthetic local forms | Provider-approved test environment/accounts, MFA enrollment, login-only permitted actions and fresh profile. No original browser profile reuse. |
| Workspace import/status/SF-424 | Routes, permissions and browser primitives | Sandbox Workspace application, expected status/import, synthetic draft-save permission and enforced no-submit boundary. |
| Email Safety bridge | Dual-admin/outage fixtures, separate-host routing contract | Actual sandbox operator/identity endpoints and dual-/single-admin negative accounts; synthetic mailbox with sending/scheduling disabled; read-only summary/recent/controls and failure checks. |
| Fresh original authenticated UI | Prior dated authorized evidence; current source/schema | Reusable authorized read-only session whose views do not mutate original records, or a separately approved change to that constraint. No new original login/account was created. |

No real email, application submission or payment was triggered. A saved donation
ledger entry or fixture acknowledgment is not a charge/email delivery. Prepared
safe runners remain in `lab/sandbox_integrations.py` and `lab/public_integrations.py`;
no unavailable credential was searched for or substituted. Synthetic WYF repair
and its conflict/idempotence/organization tests remain intact. The production
[repair plan](../WYF-REPAIR-REVIEW.md) is review-only.

## Decision

Packaging/build reproducibility: PASS within the documented external build inputs.
Functional parity: incomplete. Real integrations: BLOCKED. Production independence
from Anthesis: **no**. The configured connected topology retains central identity
and Email Safety; a replacement would require its own certified implementation.

The package is ready for review and a future synthetic trial plan, **not yet for
a connected separate-host trial or replacement**. Actual endpoints/host access,
central gateway asset/redirect validation, restricted egress and sandbox acceptance
remain gates. [Anthesis requirements](ANTHESIS.md) distinguish observed TCP reachability
from unverified HTTPS/second-host connectivity; [operations](OPERATIONS.md) provides
deployment, warmup, backup, empty-volume restore and rollback instructions.
