# Beta QA corrections

Scope: the standalone Render copy only. The original installation, existing
account roles and saved human drafts are unchanged. No submissions, email,
payments or imported external automation are enabled by this release.

| Finding | Correction | Verification and remaining limit |
|---|---|---|
| County Connections displays Tunisia requirements | Require the exact Grants.gov opportunity identity; reject unrelated keyword hits and browser redirects. Withhold mismatched cached packages from details, readiness and eligibility context. | Synthetic API, scanner and readiness regressions. The County source is an old award announcement, not a verified current package. Its actual current requirements still require funder confirmation. |
| Generated budget contradicts its line items or saved request | Check recognized currency line items, totals and requested funding before returning or saving a candidate. Buffer generated streams until validation finishes. Preserve exact cents in AI context and omit unrelated grants/applications when drafting a focused application. | Rejects the reported $26,000/$20,000 example and a $20,000 draft against a saved $100 request. Accepts exact-cent reconciliation. This is conservative validation of recognized text, not a universal financial parser. Human review remains required; existing candidates are preserved and must be reviewed or regenerated. |
| Unsupported outcome percentages | Withhold outcome percentages lacking a matching named evidence citation; allow explicit information-needed placeholders and clearly labelled proposed targets. | Synthetic supported/unsupported claim tests. This does not independently audit the truth of uploaded evidence. |
| Duplicate opportunities and stale announcements | Group exact title/agency/source identities in listings before pagination. Retain all original IDs and relationships. Mark expired deadlines, historical award announcements and unconfirmed deadlines. | Synthetic identity/round/URL tests; no destructive merge. Other ambiguous catalog records still need source review. |
| Match score changes between screens | Use the same caller-specific evidence calculation for catalog search, list, detail and workspace. Select the highest visible score for Top Match. Label manual planning assessment separately. | API consistency and frontend selection tests. Alignment is not award probability. |
| Broken Upload Documents shortcut | Open Document Ingestion with application_id in the URL and preselect that application. | Browser acceptance verifies both navigation and selection. Backend authorization still controls upload ownership. |
| Permission failures look like empty donor lists or provider outages | Explain the administrator requirement and avoid making forbidden requests for restricted roles. Distinguish actual loading failures from an empty directory. | Backend role tests and restricted-account browser checks. No role elevation. |
| Profile Complete is unconditional | Calculate completion from name, mission, email, EIN, organization type and categories instead of trusting the old Boolean flag. | Fixture with an incorrectly true legacy flag now reports incomplete. Nullable legacy lists/flags are normalized in responses without rewriting stored values. Core-field completion does not certify eligibility or compliance. |
| Prefilled planning facts | Start new partner/budget lists empty; initialize planning assessments at zero and suggested compliance checks at todo. Label templates as suggestions. | Build and UI checks. Existing saved planning profiles are retained for review, not silently rewritten. |
| Duplicate foundation directory entries | Group exact normalized name and website identities; preserve distinct entries and stored relationships. | Existing foundation lifecycle and pagination contracts. Legacy/test entries without provable identity are not deleted or treated as verified funders. |
| QA draft inflates portfolio reporting | Exclude only applications explicitly labelled both QA TEST and DO NOT SUBMIT from analytics counts and totals. | Synthetic API check proves the draft remains accessible while excluded from counts. No deletion of the user's QA artifacts. |
| Old authentication and AI documentation | Describe standalone HttpOnly sessions, server-persisted conversations, Alambda chat, reviewable candidates and paused/unconfigured external paths. Label documentation screenshots as earlier reference UI. | Production build and frontend checks. |
| Restart test schema initialization | Import MigrationSafety before building the disposable test schema. | Restart recovery tests pass without a diagnostic pre-import. |

Validation before release: a 124-test backend run and a 55-test auth/admin-contract
run passed (the runs overlap). All tests use disposable fixtures; network access
is disabled for those runs. Frontend unit tests: 11 passed. Production compilation and TypeScript validation
passed for the final frontend. Live verification results
are recorded separately from fixtures in the private operator evidence.

The older integration audit's obsolete local-JWT authentication expectations
have not been presented as passing. Role-specific admin operations, real
submissions, email, payments, mobile/accessibility and load testing are not
certified by this release. Real AI content can still need correction outside
the recognized numerical and citation checks.

Release uses feat/render-staging on the existing service. A private consistent
database/file backup is taken off-host before deployment. No schema or data
rewrite is required. Code rollback uses the prior compatible build; restoring
a data backup is a separate operation and must preserve any later user writes.

Live catalog audit: all 38 stored grants were inspected. All 24 cached packages
lacked verifiable source identity and are withheld pending source review; this
does not assert that every package is factually wrong or that a current package
has been obtained. The verified current-package gate remains explicit.

Follow-up validation: 27 profile, ownership, readiness and beta regression tests
passed, including a SQL-null legacy profile case discovered by live log review.
