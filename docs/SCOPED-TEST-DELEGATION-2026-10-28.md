# Scoped test access

The owner requested a separate test login mirroring an existing writer.
Matching organization and role alone does not grant existing applications:
the system deliberately filters them by applicant owner.

The standalone identity layer now recognizes explicit operator-managed
`auth_delegations` records. No public endpoint creates these records. A valid
delegation requires two active approved writer accounts, the same organization,
the owner's current write entitlement and an unexpired approval. Neither
account receives administrator access. Identity/credentials remain separate;
email matching does not grant access. Expiry, disabled owner, changed roles,
revoked migration entitlement or cross-organization mapping fails closed.

Existing ownership filters use the approved data owner. New on-behalf-of
records stay owned by that owner and visible in their existing account.
Mutating requests additionally record the actual signed-in actor and data
owner in a service-generated audit entry. Other owners, even in the same
organization, remain outside the delegated scope. Existing rows and credentials
are not reassigned or copied. Removing the approval restores ordinary ownership
isolation; setting its expiry in the past blocks delegated requests immediately.

The new table is additive and created by the existing schema initialization.
Without a delegation row, request behavior is unchanged. Code rollback does
not remove the test login or restore data over user edits; the prior build
simply applies its ordinary actor-only ownership filters.

Real native-session regressions cover exact owner visibility, another tenant,
another owner in the same tenant, administrator denial, on-behalf-of creation,
actor audit attribution, absent/expired approvals and immediate revocation.
Only synthetic fixtures are used in these tests.
