# Identity-link repair: review only

The synthetic tests reproduce an older writer-owned organization with nine applications and a separate central viewer projection. Real account IDs, email addresses, credential material and original-record evidence are not published here. The current production case remains unresolved; a name/email match does not authorize a link or an administrator role.

1. Independently verify the stable central identity, intended legacy owner/organization and exact owned application set. Approve the central application role separately. Do not infer global administration from an account name.
2. Under separately authorized maintenance, quiesce every writer and take consistent protected SQLite Backup API/WAL-aware backups, central-account/configuration/migration-map backups and private-file manifests. Verify restoration on protected copies.
3. Rehearse the exact conditional mapping on those copies. Preserve owner IDs and application FKs. Refuse populated/conflicting projections, ambiguous identities or conflicting migration-map rows.
4. Prepare a reviewed production-specific migration and audit/rollback record. The included `reviewed_identity_link.py` is deliberately lab-only and refuses production paths. Update central roles only through approved account-management procedures, with stale-session revocation.
5. Validate organization, exact nine-application visibility, intended edit/review permissions, cross-organization denial, logout/revocation and restart persistence. No provider actions during validation.
6. Roll back only the recorded changes if after-state still matches and no intervening writes occurred. Otherwise reconcile new writes before any complete consistent restoration; never overwrite new production writes blindly. Validate rollback before resuming writers.

The repository contains synthetic tests and a proposal, not permission to repair production.
