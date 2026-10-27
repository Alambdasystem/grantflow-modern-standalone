# Public discovery release

Owner authorized unpausing Render grant discovery on October 27, 2026.
The durable migration hold remains true. New authenticated public scrape
requests receive a server-owned `public_discovery_v1` marker. Only these
uncredentialed, application-independent searches can pass that hold.
Imported and previously queued searches are not restamped or replayed.
Renewals, portal actions, submissions and external document pickup remain held.

Both dispatcher selection and runner entry enforce this distinction. The
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

Validation: 235 isolated regression tests passed across public discovery,
beta completion, integration audit and existing fixes. TypeScript checking
and production build passed. No tests release the actual migration hold or
invoke external submissions. Live verification is recorded after deployment.

No database migration or existing-record repair is needed. Code rollback to
9ab1a6d disables this exception; it leaves any legitimately imported grants
and new job history intact. Do not restore a database over later user edits.
Original local Anthesis and GrantFlow installations remain unchanged.
