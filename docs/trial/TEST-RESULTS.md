# Readiness verification record

Observed October 25, 2026. All mutations used disposable/synthetic lab records.

| Component suite | Tests | Result |
|---|---:|---|
| test_central_identity | 2 | PASS |
| test_identity_ownership | 5 | PASS |
| test_coyf_operations | 38 | PASS |
| test_application_readiness | 7 | PASS |
| test_ingestion | 10 | PASS |
| test_ingestion_extensions | 7 | PASS |
| test_ingestion_review_tools | 3 | PASS |
| test_ingestion_workers | 3 | PASS |
| test_extended_parity | 11 | PASS |
| Identity repair, control contracts, cold/legacy, new standalone/TLS tests | 37 | PASS |
| **Current backend total** | **123** | **PASS** |
| Frontend auth/dashboard/operator unit tests | 9 | PASS |

The last row of backend tests includes 4 synthetic identity-repair, 3 control,
11 cold/legacy and 19 new readiness/transport/recovery checks. Current component
tests were executed in the lab verification image with branch source mounted.
These are not tests against real Anthesis credentials or external sandbox accounts.
The historical 109 count included five old helper checks excluded from the portable
repository; current portable base is 104, plus 19 new tests = 123. Historical
obsolete integration-suite failures remain disclosed in the baseline assessment.

New tests cover insecure trial configuration/CORS refusal; service-key rotation
and missing-file denial; model missing/unloaded/wrong digest/ready; offline SQLite
and file roundtrip; overwrite, corruption and traversal refusal; remote mTLS
requirements; actual loopback certificate/hostname/client-certificate enforcement;
explicit operator host/platform-admin denial; and raw TLS failure -> identity 503.
The loopback server uses throwaway certificates and does not verify real central
service integration. An initial TLS test exposed an unwrapped SSL exception; the
retryable handling was fixed and the affected tests passed on rerun.

Other checks:

- Clean remote main clone at 4054e69: Compose validation and both image builds PASS.
- Readiness branch: both image builds PASS (pinned base plus constrained Python/npm lock).
- Independent remote readiness clone at `71e1afd`: both builds and lab/trial
  configuration validation PASS, clean checkout afterward; see BASELINE-BUILD.md.
- Trial local and remote Compose configuration and generated Nginx syntax: PASS
  with placeholders/throwaway certificates and dummy DNS, no deployment/traffic.
- Real public unauthenticated provider reads: discovery PASS,
  requirements opportunity resolution PASS,
  public detail enrichment PASS. These ran in
  an allowlisted disposable egress runner without a database/account volume.
- Sandbox preflight: BLOCKED without approved sandbox configuration, no network
  call or credential search. No email/submission/payment action occurred.
- Resource/readiness/recreation runs: see resource-measurements.json. Historical
  strict 2 GB result remains FAIL; two candidate allocations have separate results.
- After normal-limit recreation, all five services were healthy; all nine synthetic
  legacy-owned applications, saved note and original upload hash remained intact.
  Missing authentication was denied and viewer reads remained available (six checks).

Private raw logs, traces, test XML, certificates and runtime data stay outside Git.
Published summaries exclude account data, tokens, documents and prompt content.
Packaging PASS, functional parity incomplete, eight integration/evidence gates
BLOCKED. No production WYF repair or target-host deployment was performed.
