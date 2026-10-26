# Alambda chat integration

The isolated standalone backend now supports `AI_PROVIDER=alambda`. This uses
`https://api.alambda.com/api/chat` server to server, without forwarding browser
cookies, standalone passwords, or session tokens. The original installation is unchanged.

Read-only inspection of the original Anthesis `app.py` `/api/chat` handler found
the request `{message, context, model?}` and response `{response}`. This differs
from Ollama's messages/stream protocol. Conversation roles are serialized inside
message; system instructions are sent as context. The endpoint has no native
streaming: the adapter returns a complete answer as one chunk. Model selection
defaults to the remote service, unless `ALAMBDA_MODEL` is explicitly configured;
an exact model digest cannot be verified through this contract.

## Render core configuration

`render-core.yaml` selects Alambda and the approved HTTPS URL, creates no model
container, and enables AI. A later live retry returned HTTP 200 with the exact
synthetic answer; deployed in-app verification remains required. Configure:

```dotenv
AI_PROVIDER=alambda
ALAMBDA_CHAT_URL=https://api.alambda.com/api/chat
AI_ENABLED=true
AI_INFERENCE_TIMEOUT_SECONDS=120
# Optional only if the endpoint supports a provisioned service bearer token:
ALAMBDA_API_TOKEN=
# Alternatively a mounted secret file (takes precedence):
ALAMBDA_API_TOKEN_FILE=
# Optional approved remote model name; blank uses remote default:
ALAMBDA_MODEL=
```

Keep tokens in Render secret configuration, never Git or frontend variables.
The original handler has no route-level bearer-token decorator; any service
authentication applied by its public proxy must be confirmed independently.
This adapter does not automatically sign into Anthesis as a production user.
TLS verification is enabled and redirects are rejected. Existing GrantFlow
session, role, and organization checks remain in front of AI routes.

## Verification and remaining gate

On October 26, 2026, a public synthetic POST to `/api/chat` returned **HTTP 404**;
GET `/api/tags` also returned 404. Anthesis's local login page returned 200 on
port 5000. Thus a running local application does not establish that public chat
routing works. A subsequent retry returned HTTP 200 and the requested
synthetic response, clearing public reachability. Confirm Render egress and
any required service credential during the live application test.

Contract tests use fixtures and prove serialization, TLS/redirect policy,
credential isolation, buffered output, and rejection of errors/fallbacks. They
do not prove remote AI inference. Readiness reports remote_chat_not_verified
until a successful inference, then reports that success for five minutes;
it does not generate content while polling. Empty/error/known offline fallback
responses and HTTP failures never become finished drafts. The remote contract
cannot establish exact model provenance or detect every possible fallback.

After routing is corrected, test a synthetic prompt from the Render backend,
then an authenticated GrantFlow AI workflow with synthetic context. Do not use
private grant documents for a connectivity test. Verify failure behavior and
the intended remote model before declaring real-integration readiness.
