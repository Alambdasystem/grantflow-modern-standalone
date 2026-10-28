# User journey feedback corrections

Scope: standalone beta, following the supplied Dashboard / Intake / Upload /
Review audit. The current intake is a create panel plus application detail,
not the multi-step intake described in the report. Backend internal status
updates are not evidence of submission to a funder.

| Finding | Change | Verification |
|---|---|---|
| Generic budget errors | Reject negative/nonfinite amounts before posting; label the amount input, focus invalid entry, map FastAPI field errors inline, retain all entered values and expose other server explanations. Blank remains optional; zero is valid. | Unit cases and isolated browser client/server rejection tests. |
| Upload appears stalled | Show measured byte-transfer progress, distinguish 100% transfer from server acceptance and subsequent extraction, and show a waiting notice after 15 seconds without progress. Prevent a second upload while busy, allow up to 10 minutes for a response, preserve selection on failure and explain timeout ambiguity before retry. No fabricated processing percentage. | Isolated delayed-response fixture waited beyond 15 seconds, verified one request, progress/waiting text and selection retained after failure. This does not simulate every network condition or prove large-file throughput. |
| Stale status badges | Update current application cache from successful status response; invalidate list, dashboard, analytics pipeline, renewals, workflow, reviews and readiness after relevant changes. Poll visible application list/detail/workflow every 5 seconds, dashboard every 10; recheck on window focus. Preserve unsaved proposal edits. | Cache regression and browser fixture changed server-side status while the list stayed open; card moved to Under Review without reload. Polling is bounded refresh, not push-based real time. |

Fourteen frontend tests passed, including three focused tests for this change.
TypeScript and production build passed. Three isolated browser acceptance
groups passed (field errors, status polling, delayed upload). Browser source
fixtures are explicitly separate from authenticated live acceptance.

No backend authorization, schema or stored user record is changed. Original
Anthesis is unchanged. Public discovery remains enabled for new searches;
imported external actions and funder submission stay held. OCR remains
safely capacity-blocked on the owner's 512 MB plan. Dashboard navigation is
retained; this audit does not certify external submission or award decisions.
