from __future__ import annotations
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, EmailStr, field_validator, Field
import enum


# ── Enums (mirror models) ─────────────────────────────────────────────────────

class UserRoleEnum(str, enum.Enum):
    admin = "admin"
    grant_writer = "grant_writer"
    reviewer = "reviewer"
    viewer = "viewer"


class GrantStatusEnum(str, enum.Enum):
    active = "active"
    closed = "closed"
    draft = "draft"
    archived = "archived"


class ApplicationStatusEnum(str, enum.Enum):
    draft = "draft"
    in_review = "in_review"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    renewal_due = "renewal_due"


class AutomationJobStatusEnum(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    paused = "paused"
    awaiting_approval = "awaiting_approval"


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    expires_in: int


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    role: UserRoleEnum = UserRoleEnum.grant_writer


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: UserRoleEnum
    is_active: bool
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Organization ──────────────────────────────────────────────────────────────

class OrganizationCreate(BaseModel):
    name: str
    ein: Optional[str] = None
    uei: Optional[str] = None
    description: Optional[str] = None
    mission: Optional[str] = None
    capabilities: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = "US"
    congressional_district: Optional[str] = None
    founded_year: Optional[str] = None
    org_type: Optional[str] = None
    aor_first_name: Optional[str] = None
    aor_last_name: Optional[str] = None
    aor_title: Optional[str] = None
    aor_phone: Optional[str] = None
    aor_email: Optional[EmailStr] = None
    categories: list[str] = []
    eligibility_tags: list[str] = []


class OrganizationOut(OrganizationCreate):
    id: int
    profile_complete: bool
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Grants ────────────────────────────────────────────────────────────────────

class GrantOut(BaseModel):
    id: int
    legacy_id: Optional[int]
    title: str
    description: Optional[str]
    funding_agency: Optional[str]
    amount: Optional[float]
    amount_max: Optional[float]
    deadline: Optional[datetime]
    deadline_str: Optional[str]
    eligibility: Optional[str]
    category: Optional[str]
    source_url: Optional[str]
    portal_key: Optional[str]
    status: GrantStatusEnum
    is_renewable: bool
    ai_summary: Optional[str]
    ai_match_score: Optional[float]
    catalog_state: str = 'deadline_unconfirmed'
    requirements_warning: Optional[str] = None
    tags: list[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class GrantSearch(BaseModel):
    query: Optional[str] = None
    category: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    status: Optional[GrantStatusEnum] = GrantStatusEnum.active
    is_renewable: Optional[bool] = None
    limit: int = 50
    offset: int = 0


# ── Applications ──────────────────────────────────────────────────────────────

class ApplicationCreate(BaseModel):
    grant_id: int
    organization_id: Optional[int] = None
    title: Optional[str] = None
    proposal_text: Optional[str] = None
    budget_narrative: Optional[str] = None
    amount_requested: Optional[float] = Field(default=None,ge=0,allow_inf_nan=False)
    form_data: dict[str, Any] = {}
    notes: Optional[str] = None


class ApplicationUpdate(BaseModel):
    source_draft_id: Optional[int] = None
    title: Optional[str] = None
    status: Optional[ApplicationStatusEnum] = None
    proposal_text: Optional[str] = None
    budget_narrative: Optional[str] = None
    amount_requested: Optional[float] = Field(default=None,ge=0,allow_inf_nan=False)
    amount_awarded: Optional[float] = Field(default=None,ge=0,allow_inf_nan=False)
    renewal_due_date: Optional[datetime] = None
    form_data: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


class ApplicationOut(BaseModel):
    id: int
    grant_id: int
    organization_id: Optional[int] = None
    applicant_id: Optional[int] = None
    title: Optional[str]
    status: ApplicationStatusEnum
    proposal_text: Optional[str]
    budget_narrative: Optional[str] = None
    amount_requested: Optional[float]
    amount_awarded: Optional[float]
    submission_date: Optional[datetime]
    renewal_due_date: Optional[datetime]
    ai_generated: bool
    ai_score: Optional[float]
    form_data: dict[str, Any] = {}
    notes: Optional[str] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class PlanningPriority(BaseModel):
    label: str
    weight: int
    score: int
    rationale: Optional[str] = None


class StrategicFitPayload(BaseModel):
    north_star: Optional[str] = None
    priorities: list[PlanningPriority] = []
    score: Optional[float] = None


class PlanningPartner(BaseModel):
    name: str
    role: str
    contribution: Optional[str] = None
    status: str = "target"


class BudgetLinePayload(BaseModel):
    category: str
    item: str
    quantity: float
    unit_cost: float


class ComplianceItemPayload(BaseModel):
    title: str
    owner: Optional[str] = None
    status: str = "todo"


class GrantPlanningProfileUpsert(BaseModel):
    grant_id: int
    application_id: Optional[int] = None
    strategic_fit: StrategicFitPayload = StrategicFitPayload()
    partners: list[PlanningPartner] = []
    budget_lines: list[BudgetLinePayload] = []
    compliance_items: list[ComplianceItemPayload] = []
    summary: dict[str, Any] = {}


class GrantPlanningProfileOut(BaseModel):
    id: int
    grant_id: int
    application_id: Optional[int] = None
    organization_id: Optional[int] = None
    created_by_id: Optional[int] = None
    strategic_fit: dict[str, Any] = {}
    partners: list[dict[str, Any]] = []
    budget_lines: list[dict[str, Any]] = []
    compliance_items: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GrantPlanningPromoteRequest(GrantPlanningProfileUpsert):
    application_title: Optional[str] = None


class GrantPlanningPromoteResponse(BaseModel):
    application: ApplicationOut
    planning_profile: GrantPlanningProfileOut


# ── Workflow ──────────────────────────────────────────────────────────────────

class WorkflowStageUpdate(BaseModel):
    status: str  # pending | active | completed | blocked
    notes: Optional[str] = None


class WorkflowStageOut(BaseModel):
    id: int
    application_id: int
    stage: str
    status: str
    order_index: int
    notes: Optional[str] = None

    class Config:
        from_attributes = True


# ── AI ────────────────────────────────────────────────────────────────────────

class AIGenerateRequest(BaseModel):
    application_id: Optional[int] = None
    grant_id: Optional[int] = None
    context: Optional[str] = None
    task: str = "proposal"   # proposal | executive_summary | compliance | budget | autofill
    model: Optional[str] = None
    stream: bool = False


class AIChatMessage(BaseModel):
    role: str   # user | assistant | system
    content: str


class AIChatRequest(BaseModel):
    messages: list[AIChatMessage]
    conversation_id: Optional[int] = None
    application_id: Optional[int] = None
    grant_id: Optional[int] = None
    model: Optional[str] = None
    stream: bool = False


# ── Automation ────────────────────────────────────────────────────────────────

class AutomationJobCreate(BaseModel):
    application_id: Optional[int] = None
    job_type: str                 # scrape | login | autofill | submit | renew | monitor
    portal_key: Optional[str] = None
    portal_url: Optional[str] = None
    params: dict[str, Any] = {}


class AutomationJobOut(BaseModel):
    id: int
    application_id: Optional[int]
    job_type: str
    portal_key: Optional[str]
    status: AutomationJobStatusEnum
    progress_pct: int
    current_step: Optional[str]
    steps_log: list[Any]
    screenshots: list[str]
    result: dict[str, Any]
    error_message: Optional[str]
    requires_human: bool
    human_instruction: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    @field_validator('result', mode='before')
    @classmethod
    def redact_credentials(cls, value):
        private = {'credentials', 'password', 'token', 'access_token', 'refresh_token', 'api_key', 'storage_state', 'cookies'}
        def clean(item):
            if isinstance(item, dict):
                return {k: clean(v) for k,v in item.items() if k.lower() not in private}
            if isinstance(item, list):
                return [clean(v) for v in item]
            return item
        return clean(value or {})

    class Config:
        from_attributes = True


class HumanApprovalAction(BaseModel):
    action: str   # approve | reject | retry
    note: Optional[str] = None


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: int
    title: str
    body: Optional[str]
    kind: str
    action_url: Optional[str]
    is_read: bool
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Analytics ─────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_grants: int
    active_grants: int
    total_applications: int
    submitted_applications: int
    approved_applications: int
    pending_renewals: int
    automation_jobs_running: int
    total_awarded: float
    success_rate: Optional[float]
