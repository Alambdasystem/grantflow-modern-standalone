# Honda onboarding presentation

Scoped to application 47, organization 1, grant 72 and its existing Honda
onboarding marker. Other applications retain their ordinary editor, readiness
labels and requirements controls. No backend, database, permission or file
changes are part of this release.

The Honda panel displays the saved proposed funding split, documented local
deadline with official sources and timezone caveat, four source filenames with
current extraction status, official guidance versus organizational draft
assumptions, saved character-count findings and the outstanding saved checklist.
It does not infer funding commitments, eligibility, portal requirements or a
UTC deadline. Failed attachment/checklist requests remain visibly unknown.

The blank proposal editor starts collapsed, with an explicit control to open
it. Existing nonblank or unsaved editor content remains visible. Honda replaces
the Grants.gov scanning card with the verified CyberGrants entry link. Its
existing saved-data check count is labelled onboarding completeness, explicitly
separate from eligibility, competitiveness and submission approval; the generic
requirements-presence label becomes incomplete official-guidance status.

Validation: 17 frontend unit tests passed, TypeScript and production build
passed. Browser UI fixtures passed at 1440px and 390px, including four source
statuses, funding, caveats, character counts and a collapsed empty editor.
The other-funder fixture retains its original controls. Failed-status requests
show unknown state; no browser errors or API mutations occurred in the fixtures.
Authenticated live preservation and viewport checks are recorded after release.

Unresolved source questions remain unchanged: complete portal questions/upload
inventory, tax-status and operating-budget evidence, Pacific Time/PST wording,
credential-target definitions and human review of over-length draft sections.
No proposal is generated, rewritten or saved, no extraction is approved, and
no grant or message is submitted.
