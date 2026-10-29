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

Before deploying: create a quiesced database/files backup using [the deployment runbook](RENDER-STANDALONE-DEPLOYMENT.md), retain it privately outside the application instance, verify checksums and restore/integrity in isolation, then resume service. Private-data export and brief maintenance were explicitly approved. The encrypted backup was completed and restore-verified on October 29; rollout is complete as recorded below.

Deploy the reviewed branch explicitly: the existing Render service has automatic deployment disabled. Confirm the deployed commit and additive schema version 3, then use authenticated read-only checks of the reference application and attachment hashes. Do not create analysis/review runs, modify sources or populate its blank main proposal during this preservation check.

For rollback, retain the previous deployed commit and restorable backup. The two new tables are additive and old code can ignore them. Code rollback does not restore disk/database contents. Restore only through the runbook's isolated-target process and reconcile newer data before switching paths; never overwrite a running database.

## Verified staging rollout — October 29, 2026

- Render deployment `dep-dbhl7fgu01pc73bk8b9g` reached **live** at 14:12:16 UTC (9:12 a.m. America/Chicago), running commit `ab95e3e57fa85c479e099fde5f4ad30714499fc6` on `feat/render-staging`. The service remains on its existing 512 MB plan and 1 GB disk. Automatic deployment remains off.
- The exact staging branch passed [CI run 40818952800](https://github.com/Alambdasystem/grantflow-modern-standalone/actions/runs/40818952800), including all eight environment regressions, the full backend suite, frontend tests, type-check and production build.
- The database/files backup was encrypted with AES-256-GCM before leaving Render. Its key is protected by the operator's Windows current-user DPAPI. Decryption from that protected key and restoration of all **70 files** were verified; SQLite integrity was `ok`, with **zero foreign-key violations**. Temporary plaintext verification files were removed. Keep the protected key and encrypted archive together in private retention; they are not in Git. A current-user DPAPI key requires the same Windows account/profile for recovery.
- The first local verification completed restoration but held a SQLite connection open during Windows temporary-directory cleanup. The verifier was corrected to close that connection explicitly; protected-key decryption, full restoration and cleanup then passed without taking another maintenance outage.
- Live native sign-in, the new workbench and processing-state API passed. Desktop 1440 px and mobile 390 px showed the workbench without horizontal overflow or browser exceptions. Clearing authentication cookies caused the protected workbench API to return 401.
- A fresh before/after comparison found the reference application's complete API record and source metadata unchanged. All four originals downloaded successfully with identical SHA-256 hashes; ownership, funding scopes, draft status and blank main proposal were preserved. No source analysis, generation or review run was created for that application.
- Read-only runtime inspection confirmed schema versions 2 and 3, both new workflow tables, configured Alambda AI enabled, and automatic analysis enabled for future successful associated extractions. The running reference application still has zero source-workflow runs. Existing uploads are not retroactively processed or approved just by viewing the workbench.
- Actual AI generation remains evidenced by the separate synthetic native lab journey, not by this read-only staging smoke test. This rollout did not generate a real applicant's proposal, approve held evidence, submit an application or enable external automation. OCR still needs the separately approved memory capacity/worker; passing OCR in Linux CI does not make it available on a 512 MB service.

Previous live code retained for compatible rollback: `5761dcfdc5baef7c820f258a12eb50314979a91d`. This documentation update does not change the deployed application code.

## Application readiness gates

The reference application's portal inventory is incomplete. Authorized review of the complete CyberGrants form, conditional questions/uploads/templates, limits, expense dates and cutoff wording is still required. Shared outlines are not official portal evidence. Source extraction holds remain pending an authorized reviewer; AI can analyze them as unverified drafts without approving them.

Human confirmation is needed for conflicting outcome targets and organization dates, over-length supplied sections, actual eligibility/financial evidence, credential-provider arrangements, and any claimed funding commitments. An unmet funding need must remain unmet. AI cannot create real determination letters, signed certifications, financial statements or partner commitments.

Passing automated validation is not factual certification, eligibility, competitiveness, application acceptance or submission. Export is a labelled review package; incomplete packages remain explicitly incomplete.
