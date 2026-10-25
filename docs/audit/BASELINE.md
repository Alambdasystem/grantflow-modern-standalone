# Sanitized acceptance baseline

Prior local audit: October 24, 2026. Independent repository assembly: October 25.

The original 43 feature groups plus the explicit aggregate-memory acceptance group total 44: 35 PASS, one FAIL, eight BLOCKED, zero NOT TESTED. PASS is bounded by the test scope in the matrix. Broad fixture results do not establish private real-integration acceptance. Private original account metadata, screenshots, database contents, tokens and raw reports are deliberately excluded from Git.

The old audit recorded 109 component/helper checks and nine frontend unit checks. Five safe helper selections came from a larger historical fixed-ID/production-targeted test script; that whole obsolete script is excluded from this repository. The portable current-suite runner is independently executed and counted rather than claiming those private historical checks were rerun from a clone. The unchanged old integration audit had 123 passes and 54 failures, mainly pre-central-auth assumptions; it is not the current acceptance suite.

Actual public provider reads verified Grants.gov search and nested detail parsing, Federal Register/RSS connectivity and public requirements search. Authenticated package completeness, real central identity, Email Safety, cloud folders, MFA and Workspace integration remain blocked. Synthetic nine-application identity-link tests are retained without real account data.

Cold AI first requests passed at normal limits in approximately 149 and 101 seconds. The 2,048 MiB five-container allocation failed: model cap 1,184 MiB produced an OOM kill; core workflows and valid document extraction passed. This was a container-allocation test, not a 2 GB WSL test or proof that every alternative allocation is impossible. Resource measurements for the trial will remain separate from these baseline results.

No production repair, email, application submission, charge, traffic cutover or original-service change was performed.
