# Document-to-application release verification

Date: October 28, 2026 (America/Chicago). Software deployment and an individual application's readiness are separate milestones.

## Automated verification

Tested code: `0d9cf2509389e97bb8480d1ed502456499eebcc8`.
[Linux and frontend verification run](https://github.com/Alambdasystem/grantflow-modern-standalone/actions/runs/40818492451).

- Supported Linux environment: Ubuntu 24.04 CI, pinned Python 3.12 backend image plus a dedicated verification image.
- Eight previously environment-dependent tests: **8 passed**. These cover explicit identity repair/tenant boundaries, scanned PDF and PNG OCR, backup/restore and traversal refusal, and verified TLS/client certificates. They are included in the full total below, not eight additional unique tests.
- Complete current backend suite: **450 passed, 0 failed**, 375 deprecation warnings.
- Focused document-to-application tests: **23 passed**, including three parameterized API regressions that reject missing citations, a changed participant scope, and missing-cost placeholders. Corrected synthetic revisions with supplied evidence pass approval; rejected originals remain unchanged. These are controlled fixture tests, not additional real-provider results.
- Frontend: **17 passed, 0 failed**; TypeScript check and production build passed.
- No tests were skipped or security expectations weakened. The verification image includes the existing public source-review manifest and `/ops` tools. Production images still exclude test files.

The separate native lab journey previously called the configured Alambda service for structured inventory, answer, work-plan and budget-narrative generation; persisted actual outputs; reopened TXT/DOCX/ZIP downloads; and checked native authentication, restart persistence, tenant boundaries and desktop/mobile layout. The provider produced uncited content, a participant-scope mistake and missing costs. Those outputs stayed unapproved. These observations establish real generation with synthetic data, not factual correctness or a complete real application.

## Rollout and safety gates

Target: existing `feat/render-staging` Render beta; existing single API/worker, persistent disk and 512 MB plan. No original installation, production account permissions, external submission automation, email or provider plan is changed.

Before deploying: create a quiesced database/files backup using [the deployment runbook](RENDER-STANDALONE-DEPLOYMENT.md), retain it privately outside the application instance, verify checksums and restore/integrity in isolation, then resume service. Backup export needs explicit private-data handling authorization in the current execution environment. Rollout remains pending until that gate closes.

Deploy the reviewed branch explicitly: the existing Render service has automatic deployment disabled. Confirm the deployed commit and additive schema version 3, then use authenticated read-only checks of the reference application and attachment hashes. Do not create analysis/review runs, modify sources or populate its blank main proposal during this preservation check.

For rollback, retain the previous deployed commit and restorable backup. The two new tables are additive and old code can ignore them. Code rollback does not restore disk/database contents. Restore only through the runbook's isolated-target process and reconcile newer data before switching paths; never overwrite a running database.

## Application readiness gates

The reference application's portal inventory is incomplete. Authorized review of the complete CyberGrants form, conditional questions/uploads/templates, limits, expense dates and cutoff wording is still required. Shared outlines are not official portal evidence. Source extraction holds remain pending an authorized reviewer; AI can analyze them as unverified drafts without approving them.

Human confirmation is needed for conflicting outcome targets and organization dates, over-length supplied sections, actual eligibility/financial evidence, credential-provider arrangements, and any claimed funding commitments. An unmet funding need must remain unmet. AI cannot create real determination letters, signed certifications, financial statements or partner commitments.

Passing automated validation is not factual certification, eligibility, competitiveness, application acceptance or submission. Export is a labelled review package; incomplete packages remain explicitly incomplete.
