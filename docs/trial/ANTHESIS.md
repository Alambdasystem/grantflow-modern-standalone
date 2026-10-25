# Anthesis connection contract and open gates

Observed October 25, 2026. No original record, account, service or setting was changed.

GFM owns Next.js, FastAPI, its SQLite domain data/files, automation queue/worker,
ingestion, browser agents and model integration. Anthesis provides more than the
port-5000 proxy: actual central login/token issuance, introspection, revocation
and the Email Safety operator service. The lab identity container is a synthetic
test double; it is excluded from the connected trial deployment.

| Dependency | Required connection | Security/acceptance requirement |
|---|---|---|
| Browser login/refresh | Same-origin `/auth/login`, `/api/login`, compatibility `/api/auth/login`, `/api/refresh-token` to the retained central service | Review central assets, safe `next`/redirect handling and token placement in the trial origin. Another origin cannot write this origin's localStorage. No signing keys in browser. |
| Identity | Backend POST `ANTHESIS_IDENTITY_URL` (`/api/gfm/introspect`) | Bearer plus `X-Anthesis-Service-Key`; verify TLS/hostname, active/approved identity, expiry, auth_version, app grant and role. Existing 5-second timeout; denial/outage fails closed. |
| Revocation | Backend POST `ANTHESIS_REVOKE_URL` (`/api/gfm/revoke`) | Preserve central auth_version increment and old-token rejection. This invalidates all central sessions of that identity, potentially across applications. Sandbox acceptance must confirm that intended behavior. |
| Operator role | Backend GET `ANTHESIS_PLATFORM_ME_URL` (`/api/auth/me`) | Requires central platform-admin in addition to GFM admin. |
| Email Safety | Backend GET `ANTHESIS_EMAIL_SAFETY_BASE_URL` plus `summary`, `recent`, `controls` | Bearer forwarded; 8-second timeout; read-only views and both admin gates retained. Separate explicit operator host now supported. No send/schedule mutation route exposed. |

Trial mode rejects HTTP/unapproved/localhost/.invalid central endpoints, URL
credentials or queries, permissive CORS, debug/import/admin seeding, plaintext
service-key settings and unapproved remote model transport. Secret key is read
from the mounted file on each call (rotation does not require baking an image).
TLS uses the configured CA and hostname verification; redirects are not followed.
Organization ownership remains GFM's stable identity-to-owner mapping and row
authorization. Email equality is never an account-link instruction.

Connectivity evidence is deliberately narrow: a credential-free TCP connection
from a disposable Docker container to `host.docker.internal:5000` succeeded.
This proves same-machine Docker-to-Windows TCP reachability only. No supplied
HTTPS/private DNS origin could be verified; the reply `gatw` did not specify a
URL. No actual second host, trusted certificate, DNS/firewall route, sandbox
login or operator contract has been verified. HTTP port 5000 must not be exposed
as the public solution.

Before deployment the operator must supply approved HTTPS origins, DNS/private
route/firewall rules from the actual target, CA chain, mounted service key,
trial TLS identity and synthetic central accounts. Run `deploy/connectivity.py`
from that host/network with the CA for each configured origin; this sends only
a TLS handshake. Then use `lab/sandbox_integrations.py` with its explicit sandbox
declaration/host allowlist and privately injected synthetic tokens. Test expiry,
disable/approval, app denial, writer/viewer/dual-admin roles, organization denial,
refresh, revocation and outages. A successful TLS handshake cannot close these
application gates.

The Nginx template allows only known login/refresh paths. It intentionally has no
general Anthesis fallback and does not expose introspection/revoke/operator
routes publicly. Required login assets and redirects are an explicit sandbox
gate: add only reviewed exact paths after inspecting that deployed login contract.
The template is a review candidate, not a certified replacement central gateway.
Container egress networking enables reachability but is not an outbound firewall;
target-host policy must restrict central, approved public-provider and sandbox
destinations. No original network policy was changed.

Production independence from Anthesis: **no**. Replacing central identity/email
requires a separate implementation preserving identity stability, lifecycle,
revocation, permissions and email safeguards. Disabling checks or accepting local
GFM JWTs is not an approved replacement.
