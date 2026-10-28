"""Request-local ownership filters for central identities; no background/global scope."""
from fastapi import HTTPException
from sqlalchemy import event, select, or_, false
from sqlalchemy.orm import with_loader_criteria
from config import settings
from models.models import (
    User, UserRole, Organization, GrantApplication, GrantPlanningProfile, Document,
    Review, Workflow, AutomationJob, BrowserSession, Notification, AIConversation,
    GrantAnalytic, AuditLog, DonationCampaign,
)


async def bind_identity(db, identity):
    user = (await db.execute(select(User).where(User.identity_id == identity['identity_id']))).scalar_one_or_none()
    if user is None:
        # A new central user gets a data-owner projection, never a local credential.
        import hashlib
        suffix = hashlib.sha256(identity['identity_id'].encode()).hexdigest()[:24]
        user = User(identity_id=identity['identity_id'], username='central_' + suffix,
                    email=suffix + '@identity.invalid', hashed_password='!central-identity-only!',
                    role=UserRole(identity['role']), is_active=True, is_approved=True)
        db.add(user)
        await db.flush()
    identity['local_user_id'] = user.id
    actor_id = user.id
    if settings.AUTH_MODE == 'standalone':
        from models.auth_models import AuthDelegation, MigratedAccount
        from auth.standalone import identity as native_identity
        import time
        delegation = await db.get(AuthDelegation, user.id)
        if delegation:
            owner = await db.get(User, delegation.owner_user_id)
            migrated = await db.get(MigratedAccount, delegation.owner_user_id)
            owner_identity = native_identity(owner, migrated) if owner else None
            if (delegation.expires_at <= int(time.time()) or not owner or owner.id == user.id
                    or not owner.is_active or not owner.is_approved
                    or not ((owner.identity_id or '').startswith('standalone:') or migrated)
                    or user.role.value != 'grant_writer' or identity['role'] != 'grant_writer'
                    or owner_identity['role'] != 'grant_writer'
                    or owner.organization_id != user.organization_id
                    or delegation.organization_id != user.organization_id
                    or (migrated and not migrated.permitted)
                    or set(owner_identity['grantflow_access']) != {'read', 'write'}):
                raise HTTPException(403, 'Data-owner delegation is expired, revoked or no longer authorized')
            identity['actor_user_id'] = actor_id
            identity['local_user_id'] = owner.id
    if identity['role'] == 'admin':
        return user

    uid, org = identity['local_user_id'], user.organization_id
    app_ids = select(GrantApplication.id).where(GrantApplication.applicant_id == uid)
    job_ids = select(AutomationJob.id).where(AutomationJob.created_by_id == uid)
    org_match = Organization.id == org if org is not None else false()
    criteria = {
        User: User.id == actor_id, Organization: org_match,
        GrantApplication: GrantApplication.applicant_id == uid,
        GrantPlanningProfile: GrantPlanningProfile.created_by_id == uid,
        Document: or_(Document.application_id.in_(app_ids),
                      (Document.application_id.is_(None) & (Document.organization_id == org)) if org is not None else false()),
        Review: Review.application_id.in_(app_ids), Workflow: Workflow.application_id.in_(app_ids),
        AutomationJob: AutomationJob.created_by_id == uid, BrowserSession: BrowserSession.job_id.in_(job_ids),
        Notification: Notification.user_id == uid, AIConversation: AIConversation.user_id == uid,
        GrantAnalytic: GrantAnalytic.application_id.in_(app_ids), AuditLog: AuditLog.user_id == uid,
        DonationCampaign: DonationCampaign.created_by_id == uid,
    }

    def filter_owned(execute_state):
        if execute_state.is_select or execute_state.is_update or execute_state.is_delete:
            execute_state.statement = execute_state.statement.options(*[
                with_loader_criteria(model, predicate, include_aliases=True) for model, predicate in criteria.items()
            ])

    def validate_writes(session, flush_context, instances):
        for obj in session.new.union(session.dirty).union(session.deleted):
            if isinstance(obj, User):
                raise HTTPException(403, 'Manage identities in Anthesis')
            if type(obj) not in criteria:
                continue
            for field in ('applicant_id', 'created_by_id', 'user_id'):
                if hasattr(obj, field):
                    value = getattr(obj, field)
                    if actor_id != uid and obj in session.new and value == actor_id:
                        # Separate actor attribution is recorded by get_db. New
                        # on-behalf-of records remain visible to the data owner.
                        setattr(obj, field, uid)
                        value = uid
                    if value is None and obj in session.new:
                        setattr(obj, field, uid)
                    elif value != uid:
                        raise HTTPException(403, 'Record belongs to another identity')
            if hasattr(obj, 'organization_id') and obj.organization_id is not None and obj.organization_id != org:
                raise HTTPException(403, 'Organization access denied')
            if isinstance(obj, Organization) and obj.id != org:
                raise HTTPException(403, 'Organization access denied')
            if hasattr(obj, 'application_id') and obj.application_id is not None:
                owner = session.connection().execute(select(GrantApplication.applicant_id).where(GrantApplication.id == obj.application_id)).scalar_one_or_none()
                if owner != uid:
                    raise HTTPException(404, 'Application not found')
            if isinstance(obj, BrowserSession) and obj.job_id is not None:
                owner = session.connection().execute(select(AutomationJob.created_by_id).where(AutomationJob.id == obj.job_id)).scalar_one_or_none()
                if owner != uid:
                    raise HTTPException(404, 'Job not found')

    event.listen(db.sync_session, 'do_orm_execute', filter_owned)
    event.listen(db.sync_session, 'before_flush', validate_writes)
    return user
