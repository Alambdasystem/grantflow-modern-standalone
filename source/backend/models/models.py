from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Date, JSON,
    ForeignKey, Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    grant_writer = "grant_writer"
    reviewer = "reviewer"
    viewer = "viewer"


class GrantStatus(str, enum.Enum):
    active = "active"
    closed = "closed"
    draft = "draft"
    archived = "archived"


class ApplicationStatus(str, enum.Enum):
    draft = "draft"
    in_review = "in_review"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    renewal_due = "renewal_due"


class AutomationJobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    paused = "paused"
    awaiting_approval = "awaiting_approval"


class WorkflowStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    completed = "completed"
    blocked = "blocked"


# ──────────────────────────────── Users ──────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    identity_id = Column(String(64), unique=True, nullable=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(SAEnum(UserRole), default=UserRole.grant_writer)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    is_approved = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    preferences = Column(JSON, default=dict)

    organization = relationship("Organization", back_populates="members")
    applications = relationship("GrantApplication", back_populates="applicant")
    ai_conversations = relationship("AIConversation", back_populates="user")
    notifications = relationship("Notification", back_populates="user")


# ──────────────────────────────── Organizations ───────────────────────────────

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    ein = Column(String(20))
    uei = Column(String(20))                    # SAM.gov Unique Entity Identifier (required for federal grants)
    description = Column(Text)
    mission = Column(Text)
    capabilities = Column(Text)
    website = Column(String(255))
    phone = Column(String(50))
    email = Column(String(255))
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(50))
    zip_code = Column(String(20))
    country = Column(String(50), default="US")
    congressional_district = Column(String(10))
    founded_year = Column(String(10))
    org_type = Column(String(100))
    # Authorized Organizational Representative — required to sign SF-424
    aor_first_name = Column(String(100))
    aor_last_name = Column(String(100))
    aor_title = Column(String(200))
    aor_phone = Column(String(50))
    aor_email = Column(String(255))
    categories = Column(JSON, default=list)
    eligibility_tags = Column(JSON, default=list)
    profile_complete = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    meta = Column(JSON, default=dict)

    members = relationship("User", back_populates="organization")
    applications = relationship("GrantApplication", back_populates="organization")
    documents = relationship("Document", back_populates="organization")


# ──────────────────────────────── Grants ─────────────────────────────────────

class Grant(Base):
    __tablename__ = "grants"

    id = Column(Integer, primary_key=True, index=True)
    legacy_id = Column(Integer, nullable=True, index=True)  # maps to grant_flow.db
    title = Column(String(500), nullable=False)
    description = Column(Text)
    funding_agency = Column(String(255))
    amount = Column(Float)
    amount_max = Column(Float)
    deadline = Column(DateTime(timezone=True), nullable=True)
    deadline_str = Column(String(100))
    eligibility = Column(Text)
    category = Column(String(100))
    subcategory = Column(String(100))
    source_url = Column(String(1000))
    portal_key = Column(String(100))
    status = Column(SAEnum(GrantStatus), default=GrantStatus.active)
    is_renewable = Column(Boolean, default=False)
    scraped_at = Column(DateTime(timezone=True))
    ai_summary = Column(Text)
    ai_match_score = Column(Float)
    tags = Column(JSON, default=list)
    requirements = Column(JSON, default=list)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    grant_type = Column(String(50), default="federal")  # federal | foundation | corporate | individual
    foundation_id = Column(Integer, ForeignKey("foundations.id"), nullable=True)
    requirements_detail = Column(JSON, default=dict)   # scraped package requirements from grants.gov
    requirements_fetched_at = Column(DateTime(timezone=True), nullable=True)

    applications = relationship("GrantApplication", back_populates="grant")
    analytics = relationship("GrantAnalytic", back_populates="grant")
    planning_profiles = relationship("GrantPlanningProfile", back_populates="grant")
    foundation = relationship("Foundation", back_populates="grants")


# ──────────────────────────────── Applications ───────────────────────────────

class GrantApplication(Base):
    __tablename__ = "grant_applications"

    id = Column(Integer, primary_key=True, index=True)
    legacy_id = Column(Integer, nullable=True)
    grant_id = Column(Integer, ForeignKey("grants.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    applicant_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String(500))
    status = Column(SAEnum(ApplicationStatus), default=ApplicationStatus.draft)
    proposal_text = Column(Text)
    budget_narrative = Column(Text)
    amount_requested = Column(Float)
    amount_awarded = Column(Float)
    submission_date = Column(DateTime(timezone=True))
    decision_date = Column(DateTime(timezone=True))
    renewal_due_date = Column(DateTime(timezone=True))
    source_type = Column(String(50), default="federal")     # federal | foundation | corporate | individual
    grant_period_start = Column(DateTime(timezone=True), nullable=True)
    grant_period_end = Column(DateTime(timezone=True), nullable=True)
    report_due_dates = Column(JSON, default=list)           # [{date, type, label, status}]
    year_number = Column(Integer, default=1)
    parent_application_id = Column(Integer, nullable=True)  # ID of prior-year application
    is_multi_year = Column(Boolean, default=False)
    ai_generated = Column(Boolean, default=False)
    ai_score = Column(Float)
    form_data = Column(JSON, default=dict)
    portal_submission_id = Column(String(255))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    grant = relationship("Grant", back_populates="applications")
    organization = relationship("Organization", back_populates="applications")
    applicant = relationship("User", back_populates="applications")
    documents = relationship("Document", back_populates="application")
    workflows = relationship("Workflow", back_populates="application")
    automation_jobs = relationship("AutomationJob", back_populates="application")
    reviews = relationship("Review", back_populates="application")
    planning_profiles = relationship("GrantPlanningProfile", back_populates="application")


class GrantPlanningProfile(Base):
    __tablename__ = "grant_planning_profiles"

    id = Column(Integer, primary_key=True, index=True)
    grant_id = Column(Integer, ForeignKey("grants.id"), nullable=False, index=True)
    application_id = Column(Integer, ForeignKey("grant_applications.id"), nullable=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    strategic_fit_data = Column(JSON, default=dict)
    collaboration_data = Column(JSON, default=list)
    budget_data = Column(JSON, default=list)
    compliance_data = Column(JSON, default=list)
    summary_data = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    grant = relationship("Grant", back_populates="planning_profiles")
    application = relationship("GrantApplication", back_populates="planning_profiles")


# ──────────────────────────────── Documents ──────────────────────────────────

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("grant_applications.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500))
    file_path = Column(String(1000))
    file_size = Column(Integer)
    content_type = Column(String(100))
    document_type = Column(String(100))  # budget, proposal, narrative, 990, etc.
    ai_summary = Column(Text)
    extracted_text = Column(Text)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    application = relationship("GrantApplication", back_populates="documents")
    organization = relationship("Organization", back_populates="documents")


class ApplicationSourceRun(Base):
    """Immutable successful outputs; retries only replace failed attempts."""
    __tablename__ = 'application_source_runs'
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False, index=True)
    application_id = Column(Integer, ForeignKey('grant_applications.id'), nullable=False, index=True)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    request_key = Column(String(64), nullable=False, unique=True)
    kind = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False, default='queued')
    inputs = Column(JSON, default=dict)
    sources = Column(JSON, default=list)
    output = Column(JSON, default=dict)
    provider = Column(String(100))
    model = Column(String(255))
    error = Column(Text)
    attempts = Column(Integer, default=0)
    progress = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    started_at = Column(DateTime)
    finished_at = Column(DateTime)


class ApplicationSourceReview(Base):
    __tablename__ = 'application_source_reviews'
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False, index=True)
    run_id = Column(Integer, ForeignKey('application_source_runs.id'), nullable=False, index=True)
    item_key = Column(String(100), nullable=False)
    actor_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    decision = Column(String(30), nullable=False)
    notes = Column(Text, nullable=False)
    source_url = Column(String(2000), default='')
    output_hash = Column(String(64), nullable=False)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, server_default=func.now())


class IngestionSource(Base):
    __tablename__ = 'ingestion_sources'
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False, index=True)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    label = Column(String(255), nullable=False)
    enabled = Column(Boolean, default=False)
    interval_seconds = Column(Integer, default=3600)
    next_poll = Column(DateTime)
    last_poll = Column(DateTime)
    last_success = Column(DateTime)
    error = Column(Text)
    history = Column(JSON, default=list)


class IngestionDocument(Base):
    __tablename__ = 'ingestion_documents'
    __table_args__ = (UniqueConstraint('organization_id', 'logical_key', 'version'),)
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False, index=True)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    source_id = Column(Integer, ForeignKey('ingestion_sources.id'))
    document_id = Column(Integer, ForeignKey('documents.id'))
    grant_id = Column(Integer, ForeignKey('grants.id'))
    logical_key = Column(String(64), nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(30), default='queued')
    current = Column(Boolean, default=True)
    category = Column(String(100), default='general')
    extracted = Column(JSON, default=dict)
    history = Column(JSON, default=list)
    error = Column(Text)
    attempts = Column(Integer, default=0)
    retry_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    checked_at = Column(DateTime, server_default=func.now())
    reviewed_at = Column(DateTime)
    reviewed_by = Column(Integer)
    evidence_date = Column(Date)
    review_due = Column(Date)


class IngestionCorrection(Base):
    __tablename__ = 'ingestion_corrections'
    id = Column(Integer, primary_key=True)
    ingestion_id = Column(Integer, ForeignKey('ingestion_documents.id'), nullable=False, index=True)
    organization_id = Column(Integer, nullable=False, index=True)
    actor_id = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    before_text = Column(Text, nullable=False)
    after_text = Column(Text, nullable=False)
    before_revision = Column(String(64), nullable=False)
    after_revision = Column(String(64), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class IngestionWorkerHeartbeat(Base):
    __tablename__ = 'ingestion_worker_heartbeats'
    worker_id = Column(String(100), primary_key=True)
    seen_at = Column(DateTime, nullable=False)


class DocumentChunk(Base):
    __tablename__ = 'document_chunks'
    id = Column(Integer, primary_key=True)
    ingestion_id = Column(Integer, ForeignKey('ingestion_documents.id'), nullable=False, index=True)
    organization_id = Column(Integer, nullable=False, index=True)
    locator = Column(String(255))
    text = Column(Text, nullable=False)


class DocumentUse(Base):
    __tablename__ = 'document_uses'
    id = Column(Integer, primary_key=True)
    ingestion_id = Column(Integer, ForeignKey('ingestion_documents.id'), nullable=False, index=True)
    organization_id = Column(Integer, nullable=False, index=True)
    target_type = Column(String(50), nullable=False)
    target_id = Column(Integer, nullable=False)
    field = Column(String(50), nullable=False)


# ──────────────────────────────── Reviews ────────────────────────────────────

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("grant_applications.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    score = Column(Float)
    feedback = Column(Text)
    ai_feedback = Column(Text)
    criteria = Column(JSON, default=dict)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    application = relationship("GrantApplication", back_populates="reviews")


# ──────────────────────────────── Workflows ──────────────────────────────────

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("grant_applications.id"), nullable=False)
    stage = Column(String(255))
    status = Column(SAEnum(WorkflowStatus), default=WorkflowStatus.pending)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    application = relationship("GrantApplication", back_populates="workflows")


# ──────────────────────────────── Automation ─────────────────────────────────

class AutomationJob(Base):
    __tablename__ = "automation_jobs"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("grant_applications.id"), nullable=True)
    job_type = Column(String(100))       # scrape | login | autofill | submit | renew | monitor
    portal_key = Column(String(100))     # grants_gov | justgrants | sam_gov | custom
    portal_url = Column(String(1000))
    status = Column(SAEnum(AutomationJobStatus), default=AutomationJobStatus.queued)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    progress_pct = Column(Integer, default=0)
    current_step = Column(String(255))
    steps_log = Column(JSON, default=list)
    screenshots = Column(JSON, default=list)
    result = Column(JSON, default=dict)
    error_message = Column(Text)
    requires_human = Column(Boolean, default=False)
    human_instruction = Column(Text)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    application = relationship("GrantApplication", back_populates="automation_jobs")


class BrowserSession(Base):
    __tablename__ = "browser_sessions"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("automation_jobs.id"), nullable=True)
    portal_key = Column(String(100))
    session_state = Column(JSON, default=dict)   # cookies, storage, etc. — encrypted
    is_active = Column(Boolean, default=False)
    last_used = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ──────────────────────────────── Notifications ──────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(Text)
    kind = Column(String(50), default="info")  # info | warning | success | error
    action_url = Column(String(500))
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="notifications")


# ──────────────────────────────── AI ─────────────────────────────────────────

class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    application_id = Column(Integer, ForeignKey("grant_applications.id"), nullable=True)
    grant_id = Column(Integer, ForeignKey("grants.id"), nullable=True)
    context = Column(String(100), default="general")
    messages = Column(JSON, default=list)
    model_used = Column(String(100))
    token_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="ai_conversations")


# ──────────────────────────────── Analytics ──────────────────────────────────

class GrantAnalytic(Base):
    __tablename__ = "grant_analytics"

    id = Column(Integer, primary_key=True, index=True)
    grant_id = Column(Integer, ForeignKey("grants.id"), nullable=False)
    application_id = Column(Integer, ForeignKey("grant_applications.id"), nullable=True)
    view_count = Column(Integer, default=0)
    apply_count = Column(Integer, default=0)
    success_rate = Column(Float)
    avg_award = Column(Float)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())

    grant = relationship("Grant", back_populates="analytics")


# ──────────────────────────────── Audit ──────────────────────────────────────

class OrganizationRecord(Base):
    """Versioned organizational knowledge, partnerships, audits and configuration."""
    __tablename__ = "organization_records"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    kind = Column(String(30), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, default="")
    data = Column(JSON, default=dict)
    revision = Column(Integer, default=1, nullable=False)
    history = Column(JSON, default=list)
    __mapper_args__ = {"version_id_col": revision, "version_id_generator": False}
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(255), nullable=False)
    resource_type = Column(String(100))
    resource_id = Column(Integer)
    details = Column(JSON, default=dict)
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ─────────────────────────────── Portal Credentials ──────────────────────────

class PortalCredential(Base):
    __tablename__ = "portal_credentials"

    id = Column(Integer, primary_key=True, index=True)
    portal_key = Column(String(100), nullable=False, unique=True, index=True)
    portal_name = Column(String(255), nullable=False)
    portal_url = Column(String(1000))
    credential_type = Column(String(50), default="username_password")  # username_password | api_key
    username = Column(String(255))
    password_b64 = Column(Text)      # base64-encoded password (not real encryption)
    api_key_b64 = Column(Text)       # base64-encoded API key
    is_connected = Column(Boolean, default=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    last_login_status = Column(String(50))    # success | failed | pending
    last_job_id = Column(Integer, nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ──────────────────────────── Foundations ─────────────────────────────────────

class Foundation(Base):
    __tablename__ = "foundations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    website = Column(String(500))
    grant_type = Column(String(50), default="private")   # private | community | corporate | family | public
    focus_areas = Column(JSON, default=list)
    geographic_focus = Column(Text)
    portal_type = Column(String(50), default="website")  # submittable | fluxx | zoomgrants | email | website | other
    portal_url = Column(String(500))
    portal_key = Column(String(100))
    typical_amount_min = Column(Float)
    typical_amount_max = Column(Float)
    accepts_unsolicited = Column(Boolean, default=True)
    requires_loi = Column(Boolean, default=False)
    loi_deadline_days_before = Column(Integer, default=60)
    cycle = Column(String(50), default="rolling")        # rolling | annual | biannual | invite-only
    eligibility_notes = Column(Text)
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    meta = Column(JSON, default=dict)

    contacts = relationship("FoundationContact", back_populates="foundation", cascade="all, delete-orphan")
    grants = relationship("Grant", back_populates="foundation")


class FoundationContact(Base):
    __tablename__ = "foundation_contacts"

    id = Column(Integer, primary_key=True, index=True)
    foundation_id = Column(Integer, ForeignKey("foundations.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    title = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    is_primary = Column(Boolean, default=False)
    relationship_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    foundation = relationship("Foundation", back_populates="contacts")


# ──────────────────────────── Donors & Campaigns ──────────────────────────────

class Donor(Base):
    __tablename__ = "donors"

    id = Column(Integer, primary_key=True, index=True)
    donor_type = Column(String(50), default="individual")  # individual | business | foundation | government | other
    first_name = Column(String(100))
    last_name = Column(String(100))
    organization_name = Column(String(255))
    email = Column(String(255), index=True)
    phone = Column(String(50))
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(50))
    zip_code = Column(String(20))
    country = Column(String(50), default="US")
    is_anonymous = Column(Boolean, default=False)
    total_donated = Column(Float, default=0.0)
    tags = Column(JSON, default=list)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    meta = Column(JSON, default=dict)

    donations = relationship("Donation", back_populates="donor")


class DonationCampaign(Base):
    __tablename__ = "donation_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    goal_amount = Column(Float)
    raised_amount = Column(Float, default=0.0)
    campaign_type = Column(String(50), default="general")  # general | capital | program | event | emergency
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=True)
    thank_you_message = Column(Text)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    meta = Column(JSON, default=dict)

    donations = relationship("Donation", back_populates="campaign")


class Donation(Base):
    __tablename__ = "donations"

    id = Column(Integer, primary_key=True, index=True)
    donor_id = Column(Integer, ForeignKey("donors.id"), nullable=True)
    campaign_id = Column(Integer, ForeignKey("donation_campaigns.id"), nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")
    donation_type = Column(String(50), default="cash")  # cash | check | in-kind | stock | pledge | grant-award | wire
    is_restricted = Column(Boolean, default=False)
    restriction_purpose = Column(Text)
    received_at = Column(DateTime(timezone=True), nullable=True)
    is_anonymous = Column(Boolean, default=False)
    acknowledgment_sent = Column(Boolean, default=False)
    acknowledgment_sent_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    meta = Column(JSON, default=dict)

    donor = relationship("Donor", back_populates="donations")
    campaign = relationship("DonationCampaign", back_populates="donations")
