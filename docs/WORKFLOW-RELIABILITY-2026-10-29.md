# Source workflow reliability review release

This release is prepared for review, not deployed. It changes no account, original installation, source attachment, main proposal or existing approved draft.

## Changes

- Bound draft evidence selection and inventory batches. Keep exact excerpts, relevant worksheet tables, explicit omissions and source hashes; never describe selected context as complete coverage.
- Persist inventory checkpoints and AI call metadata. Retry failed jobs without reprocessing completed batches. A completed partial inventory can retry withheld batches as a separate version.
- Normalize equivalent JSON wrapper shapes while retaining strict field, quotation, question and source-locator checks. Unsupported items remain withheld.
- Preserve original and correction candidates. Make one recorded correction attempt for substantive validation errors; leave failed checks visible and block approval.
- Recognize information-needed placeholders with explanatory text.
- Keep initiating job actor separate from original source creator.
- Add version-linked AI regeneration and call history in the workbench.
- Add an explicit unapproved review export, with labelled TXT/DOCX, validation, manifest, originals and portal instructions. Preserve drafts from earlier inventories without claiming they answer newly extracted requirements.
- Refuse inventory completeness and submission readiness while source batches remain withheld.

No schema migration is required: checkpoints and execution records use existing versioned JSON fields. The existing default approved-content export is retained.

## Evidence and limitations

The configured Alambda service was called for real on an isolated Linux copy of actual source documents and existing draft history. The live database was not used as the replay database. An inventory run completed 40 batches / 220 source parts, producing 190 provisional items after 55 model calls; five batches remained withheld. These are model-proposed extractions, not 190 verified portal requirements.

Three initial drafts and three traceable subsequent revisions completed. One automatic correction was attempted for each subsequent revision, preserving both candidates. The resulting drafts still had citation/numerical validation errors. The release therefore improves processing reliability and fail-closed review; it does not establish reliable autonomous application authorship.

The native review export included and reopened 31 labelled DOCX drafts, preserving earlier inventory work. Real public Grants.gov discovery imported two opportunities into an isolated catalog; repeating discovery updated two without duplicate insertion, and application search returned an imported record. The live shared catalog was not modified.

Honda's public quiz entry uses a JavaScript jump to a public question. Only that question was inspected; no quiz answers, certifications, account creation, uploads or submission were attempted. The authenticated complete form is unavailable.

Private source documents, full responses, account data, screenshots and replay artifacts remain outside Git under the ignored .private directory.

## Regression evidence

The full Windows backend suite contains 454 tests: 449 pass; five environment-dependent failures concern guarded Linux-only identity repair, OCR dependencies and OpenSSL/TLS tooling. Linux separately passes 50 focused workflow, identity, backup and TLS tests, including the three non-OCR Windows failures. OCR remains unverified under the approved memory constraint; no tests were weakened or silently skipped.

Frontend: 17 unit tests pass; TypeScript and production build pass. Fixture regressions prove contracts and security gates, not real integration behavior. The actual-provider/source replay is separate evidence.

## Deployment dependency and rollback

Merge into the Render-connected deployment branch only after release review. The current live version remains unchanged. Before deployment, create and privately restore-test a fresh encrypted database/uploads snapshot; no production record repair is part of this release.

After deployment, verify the deployed commit, normal owner login, unchanged source hashes/budget/main proposal, existing draft visibility, withheld-batch retry, separate revision generation and both export modes. Run only explicitly selected revisions; do not regenerate every historical draft automatically.

Rollback uses the prior compatible application artifact. Never overwrite database/files with an earlier snapshot without separately reviewing intervening writes. Existing outputs and failures must remain preserved.

## Work still required

1. Obtain the complete authorized portal form and conditional requirements; supplied outlines cannot establish completeness.
2. Improve real model citation/number/length compliance and calibrated source matching. Acceptance requires real-provider drafts that pass server checks while retaining genuine missing-input warnings and factual conflicts.
3. Protect provider credentials with tenant-scoped secret references. The current base64 storage and job payload handling are not an acceptable future automated-portal secret boundary.
4. Add canonical provider/opportunity IDs, consistent deduplication, refresh provenance and explicit scheduling. The portal metadata list is not a discovery plugin registry.
5. Implement provider-specific upload/save-draft/status contracts only where authorized and officially supported; generic browser form filling is not proof of submission or reconciliation capability.
