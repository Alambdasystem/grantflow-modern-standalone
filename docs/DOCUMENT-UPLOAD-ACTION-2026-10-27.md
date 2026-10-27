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

This is a frontend-only release: no schema, stored records, account permissions,
external automation or service allocation changes. OCR remains safely blocked
on the existing 512 MB allocation by the owner's decision. Prior beta audit
integration gates remain open; this change does not certify full parity.
