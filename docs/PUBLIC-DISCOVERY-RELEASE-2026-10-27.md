# Public discovery release

Owner authorized unpausing Render grant discovery on October 27, 2026.
The durable migration hold remains true. New authenticated public scrape
requests receive a server-owned `public_discovery_v1` marker. Only these
uncredentialed, application-independent searches can pass that hold.
Imported and previously queued searches are not restamped or replayed.
Renewals, portal actions, submissions and external document pickup remain held.

Dispatcher selection, runner entry and orchestrator entry enforce this distinction. The
dispatcher filters held jobs before applying its batch limit so older jobs
cannot starve new searches. Interrupted public searches pause for explicit
retry; ingestion keeps its existing bounded recovery behavior.

Public discovery uses the existing public HTTP sources and never launches a
browser process on this release path. It requires no funder password. Search
in the catalog filters stored data; Discover New Grants queues a fresh search.
This enables on-demand discovery, not scheduled synchronization. Existing
source URLs are still skipped by the importer, so an old saved record is not
automatically revalidated. Source association, eligibility and deadline checks
remain separate. Imported results are not certified open or submit-ready.

Validation: 236 isolated regression tests passed across public discovery,
beta completion, integration audit and existing fixes. TypeScript checking
and production build passed. No tests release the actual migration hold or
invoke external submissions. Live verification is recorded after deployment.
The first live search exposed a third hold at orchestrator entry; it safely
paused the search. The correction includes a test through the real
orchestrator with only its public HTTP source fixture substituted. That test
proves an old job stays paused and a new public job completes and imports once.

No database migration or existing-record repair is needed. Code rollback to
9ab1a6d disables this exception; it leaves any legitimately imported grants
and new job history intact. Do not restore a database over later user edits.
Original local Anthesis and GrantFlow installations remain unchanged.

## Live result

Render deploy `dep-dbgh52egekts738ocu20` reached live at 2026-10-27
21:08:22 UTC, commit `6d407b1f89ee923c2d40482c9322185404a7c74a`.
An isolated native writer signed in through the visible browser, entered
`youth education`, and clicked Discover New Grants. Job 62 completed actual
public HTTP discovery: 33 source results, 33 grants added. Progress recorded
Grants.gov API, Federal Register API and Grants.gov RSS requests without
reported source errors. No fixture substituted these live requests.

Runtime still reported `external_jobs_paused: true`; every older non-ingestion,
non-public-discovery job returned the same status before and after the test.
Public search requires no portal credentials, emails, payments or submissions.
New listings remain source leads, not verified current submission packages.
The initial paused job 61 is retained as failed-release diagnostic history;
it was not replayed. Genuine public catalog imports are retained for research.
