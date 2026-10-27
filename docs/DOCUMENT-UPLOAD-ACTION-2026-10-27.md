# Documents upload action

The Documents page had no header upload action or icon. Its upload form was
below historical documents and the processing monitor, making it difficult
to find as document history grew.

The header now includes an Upload document action and icon. It scrolls to
the upload panel and focuses the file chooser. The panel precedes history
and monitoring; file selection has an explicit styled control. Viewer
accounts receive a read-only explanation, and identity lookup failures are
reported instead of silently hiding the form. Server authorization is unchanged.

Validation: 11 frontend unit tests passed; TypeScript and production build
passed. `lab/document_upload_action_check.py` passed four isolated browser
checks: writer and viewer at 1440px and 390px. These use UI fixtures and
verify visibility, icon, keyboard focus, file selection, enabled submission,
upload-panel order and absence of horizontal overflow. They do not prove
server-side extraction. Live deployment checks are recorded separately.

Live verification: Render deploy `dep-dbggtp8m7kps73dchq30` reached `live`
at 2026-10-27 20:53:55 UTC with commit
`9ab1a6d6c64b3aa7a5c48d7c96f5fdeda4b09f8b`. Four authenticated browser
checks passed on that deployment (writer/viewer, 1440px/390px). A separate
visible writer upload of a disposable synthetic TXT file returned 202,
completed actual extraction to ready, downloaded byte-for-byte identically,
and remained visible after page reload. The disposable document was removed
through the supported administrator DELETE endpoint. No existing document
was edited or removed. An initial browser attempt during deployment timed
out waiting for login; the complete check passed after Render reported live.

This is a frontend-only release: no schema, stored records, account permissions,
external automation or service allocation changes. OCR remains safely blocked
on the existing 512 MB allocation by the owner's decision. Prior beta audit
integration gates remain open; this change does not certify full parity.
