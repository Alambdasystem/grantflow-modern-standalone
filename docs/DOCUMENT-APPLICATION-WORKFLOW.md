# Document-to-application workbench

Implementation is prepared in the isolated lab. No Render deployment is part of this change. Do not push the connected deployment branch until review and deployment authorization.

## Flow

The application detail page contains **Documents to application**. Upload source documents with an application association using Document Ingestion. Original bytes and hashes remain unchanged. DOCX extraction retains hyperlink text/targets and tables, PDF extraction retains page links, and sources keep paragraph/page/table locators. Reprocessing changed text records before/after transcription snapshots; it does not approve extraction.

With `AI_ENABLED=true` and `APPLICATION_SOURCE_AUTO_ANALYZE=true`, completion of an associated extraction batch queues requirements analysis. A failed source prevents automatic analysis of an apparently complete batch. The user can also select extracted sources and explicitly analyze them, including held sources as **unverified drafts**. New origins default to supplied outlines; a user declaration of official guidance is not verification. Set automatic analysis false when only explicit generation is wanted.

The inventory is AI-generated structured data, bounded by complete source batches. Every item carries a source quotation, locator, document version, hash, origin and review state. Exact-question quotations are checked server-side; unsupported/invented questions and invalid structured responses fail the job. The system never automatically declares the inventory complete. Source batches are not silently truncated; excessive source sets fail with a request to select smaller groups.

The selected organizational evidence and profile produce **lexical suggestions**, not semantic proof or eligibility decisions. A reviewer can mark supported, partially supported, missing, conflicting or awaiting confirmation. Every suggested match shows its source excerpt or profile field. Application-specific access and organization checks apply to every route. Sources from other applications cannot be selected as this application's evidence; organization-level documents can be explicitly selected.

Generate separate answer, narrative, budget narrative, work-plan or evaluation-plan candidates from draftable requirements. Original attachments and the main proposal are never edited by this workflow. Work plans must leave unsupplied dates/owners as information-needed placeholders. Proof documents such as signed certifications, financial statements, determination letters, tax returns and partner commitments are human-supplied. Required narrative/work-plan uploads can have AI-drafted content, but proof and portal formats still require review.

Human edits create new immutable candidate versions. Reviewer decisions record actor, time, output hash, notes, source URL and evidence assessment; review history is available at the run reviews endpoint. Reviewer source confirmation is separate from portal confirmation. Marking a complete inventory requires review of every item, confirmed applicability and portal-confirmed questions, uploads and templates. A held extraction cannot be silently promoted to verified evidence by accepting its requirement item.

## Validation and exports

Server checks apply to generation, revisions, acceptance and exports. They cover declared character/word limits (`under 2,000` means fewer than 2,000), source references, numeric claims, request/overall/gap scopes, arithmetic, missing-information placeholders, unresolved inventory conflicts, stale source/context versions, missing required answers and missing reviewed uploads. Automated checks are conservative and do not certify semantic truth. All candidates require human review.

Individual TXT/DOCX downloads are labelled unapproved/approved/stale and include validation information. A package ZIP contains approved answer versions in TXT/DOCX, available originals/supporting files, a requirement-to-file manifest with hashes, and an outstanding-items checklist. Pending or failed newer inventories cannot silently be replaced by an older complete package. Incomplete packages say **INCOMPLETE**; unapproved answers are excluded. Files may belong in separate CyberGrants or other portal fields. Export never submits anything or measures competitiveness.

Existing application readiness additionally checks any workbench requirements. Legacy generic requirements alone no longer make package completeness true. The main application's human review remains separate.

Existing application acceptance and protected status transitions also check the workbench. An older accepted main-proposal review cannot bypass newly pending source requirements. A funder's own instructions cannot be used as evidence that the organization satisfies those instructions; matching suggestions exclude those sources from organizational proof.

## Storage, jobs and rollout

SQLite startup adds `application_source_runs` and `application_source_reviews` transactionally via the existing reviewed metadata creation and records schema version3. Existing tables/records are retained. Jobs and outputs live on the same persistent database; originals remain in configured ingestion storage. Successful runs are immutable; request/source/context fingerprints deduplicate repeated actions. Failed/interrupted jobs need explicit retry (at most three attempts). Restart recovery does not overwrite completed/approved work. Source, profile or funding changes invalidate dependent review.

The separate internal worker starts with the API. It neither enables external portal automation nor sends email. Provider and configured model identifiers are saved with each AI run, along with source versions, progress, error, attempts and output reference. Alambda currently does not expose independently verified model identity; the UI must retain that limitation. Safe provider diagnostics report error classes or HTTP status only, never credentials or response bodies. After three failed attempts, a reviewer/operator must record the incident resolution to create a separate recovery run; the failed run and any approved outputs remain intact. Repeated recovery requests are deduplicated. Failure to enqueue AI analysis leaves successful extraction and its review hold intact, with a visible queue warning.

The current dispatcher assumes one API/worker process and one persistent SQLite instance. Use leases/dedicated coordination before introducing multiple API workers or replicas. Do not scale this worker topology horizontally as-is.

For funders using complete official PDF forms rather than a portal, a reviewer can explicitly choose the official-complete-form basis and cite its HTTPS source. Questions/uploads must originate in official documents; supplied outlines and AI suggestions cannot establish that basis. Honda's known incomplete onboarding remains portal-gated. Neither basis is selected or confirmed by AI.

Before any future deployment: take and verify a database/file backup using the existing deployment runbook; review the additive schema diff, automatic-analysis setting and AI credentials. Test a restored copy. Preserve the old image for rollback; the old app can ignore the two new tables. Restore the matching backup only through the existing reviewed restore process if needed, retaining post-backup data for reconciliation. This change performs no live data repair or reprocessing.

For other funders, optional saved `form_data.funding_plan` can provide `program_total` and `unmet_funding`; requested funding remains the authoritative application amount. The existing Honda onboarding budget fields are read compatibly. Do not confuse an organization's annual operating budget with a program budget or treat unmet funding as committed.

## Reference-case limits and test evidence

The private Honda audit and implementation evidence remain outside Git. In offline replay, the five omitted outline links are recovered and original hashes match; the outline and workbook still require review. Known character-count, credential-target, founding-year and timezone conflicts remain visible. Full portal questions/uploads/templates/expense dates still need authorized confirmation. No live Honda proposal, source approval, submission or message was created.

Real Alambda inventory and draft calls were exercised locally with synthetic sources, separate from provider-fixture unit tests. Generated output persisted in a fresh SQLite database and actual TXT/DOCX download routes and ZIP manifests were reopened. Initial provider/schema failures are retained as evidence rather than counted as successes. Initial layout checks used labelled synthetic HTTP fixtures; the additional native journey below also verified layout without response fixtures. See the local implementation report for exact final totals and remaining platform-dependent test failures.

The additional native end-to-end harness uses real native login/logout, real HTTP requests, extraction/internal workers and the real configured Alambda service; its browser proxy forwards responses unchanged. It creates only a marked synthetic local database and a private generated test credential file. It does not access the existing installation or Render records. Read the scripts before running:

1. Confirm ports8311 and3109 are free. Use the project's installed Python dependencies, frontend dependencies, Chrome and Playwright.
2. In one terminal run `python lab/source_workflow_native_server.py`. This creates `.private/source-workflow-native`; do not replace its marked database with production data.
3. Build the frontend and start it on local port3109: `node node_modules/next/dist/bin/next start --port 3109 --hostname 127.0.0.1` from `source/frontend`. The test browser forwards API calls to8311, preserving actual backend responses, native cookies and CSRF checks.
4. Run `python lab/verify_source_workflow_native.py`. It signs in through the real UI, creates clearly labelled synthetic application/source records, waits for real AI jobs, checks automatic/manual deduplication, downloads/reopens TXT/DOCX/ZIP, checks desktop/mobile, verifies a held source stays unapproved, preserves the main proposal and rejects access after logout.
5. Stop only these two test processes. Results and generated test credentials stay under `.private`; do not commit them. The harness has real model-call cost and may legitimately fail when the provider is unavailable or returns unsupported requirements. It never substitutes a fixture response.

Real generation also exposed a semantic error: a model changed twenty participants **in total** into twenty **per workshop**. A focused server guard and regression now flag that scope change. General semantic accuracy still requires human review; passing arithmetic/length/citation checks does not prove every sentence true.
