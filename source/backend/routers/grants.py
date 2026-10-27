"""Grants CRUD + live discovery + match scoring."""
import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from db.database import get_db, AsyncSessionLocal
from models.models import Grant, GrantStatus, Organization, User, OrganizationRecord
from schemas.schemas import GrantOut, GrantSearch
from auth.jwt_handler import get_current_user_token, require_admin
from pydantic import BaseModel, Field, HttpUrl
from automation.agents.grant_scraper import GrantScraperAgent

router = APIRouter(prefix="/api/grants", tags=["grants"])
from services.grant_integrity import deduplicate, catalog_state, requirement_error, safe_requirements, opportunity_id


async def personalized(db, token, grants):
    from routers.operations import alignment, organization_evidence
    user = (await db.execute(select(User).where(User.identity_id == token['identity_id']).limit(1))).scalar_one_or_none()
    org = await db.get(Organization, user.organization_id) if user and user.organization_id else None
    records, documents = await organization_evidence(db, org.id) if org else ([], [])
    results = []
    for grant in grants:
        item = GrantOut.model_validate(grant)
        item.catalog_state = catalog_state(grant)
        item.requirements_warning = requirement_error(grant)
        if item.requirements_warning:
            item.eligibility = None
        match = alignment(org, grant, records, documents) if org else None
        item.ai_match_score = match['score'] if match else None
        item.ai_summary = ('Evidence alignment, not award probability. Missing: ' + ', '.join(match['missing_information'])) if match else 'Assign an organization before calculating personalized alignment.'
        results.append(item)
    return results


class ManualOpportunity(BaseModel):
    title: str = Field(min_length=3,max_length=500)
    funding_agency: str = Field(default='',max_length=255)
    description: str = Field(default='',max_length=20000)
    source_url: HttpUrl | None = None
    amount: float | None = Field(default=None,ge=0,allow_inf_nan=False)


@router.post('/',response_model=GrantOut,status_code=201)
async def create_opportunity(payload:ManualOpportunity,db:AsyncSession=Depends(get_db),identity:dict=Depends(require_admin)):
    record=Grant(**payload.model_dump(exclude={'source_url'}),source_url=str(payload.source_url) if payload.source_url else None,
                 status=GrantStatus.active,category='General',tags=[])
    db.add(record);await db.commit();await db.refresh(record)
    return record


@router.get('/{grant_id}/workspace')
async def grant_workspace(grant_id: int, db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    from models.models import GrantApplication, Document, Review, Workflow
    from routers.operations import scope, organization_evidence, alignment
    grant = await db.get(Grant, grant_id)
    if not grant:
        raise HTTPException(404, 'Grant not found')
    _, org = await scope(db, token)
    records, documents = await organization_evidence(db, org.id)
    apps = (await db.execute(select(GrantApplication).where(GrantApplication.grant_id == grant_id,
        GrantApplication.organization_id == org.id).order_by(GrantApplication.updated_at.desc()))).scalars().all()
    ids = [a.id for a in apps]
    reviews = (await db.execute(select(Review).where(Review.application_id.in_(ids)).order_by(Review.id.desc()))).scalars().all() if ids else []
    workflows = (await db.execute(select(Workflow).where(Workflow.application_id.in_(ids)))).scalars().all() if ids else []
    app_documents = (await db.execute(select(Document).where(Document.application_id.in_(ids)))).scalars().all() if ids else []
    all_docs = {d.id:d for d in [*documents,*app_documents]}
    return {'grant':(await personalized(db,token,[grant]))[0], 'alignment':alignment(org,grant,records,documents),
        'requirements':safe_requirements(grant) or ([] if requirement_error(grant) else grant.requirements or []),
        'requirements_warning':requirement_error(grant),
        'requirements_fetched_at':grant.requirements_fetched_at,
        'applications':[{'id':a.id,'title':a.title,'status':a.status.value,'updated_at':a.updated_at,
                         'renewal_due_date':a.renewal_due_date} for a in apps],
        'reviews':[{'id':r.id,'application_id':r.application_id,'status':r.status,'feedback':r.feedback,'created_at':r.created_at} for r in reviews],
        'workflows':[{'application_id':w.application_id,'stage':w.stage,'status':w.status} for w in workflows],
        'documents':[{'id':d.id,'title':d.original_filename or d.filename,'type':d.document_type} for d in all_docs.values()]}

DISCOVERY_STOP_WORDS = {
    "the", "and", "for", "with", "that", "from", "this", "into", "your", "their", "will", "have",
    "program", "programs", "initiative", "services", "county", "youth", "grant", "foundation", "education",
    "world", "students", "student", "community", "support", "nonprofit",
}


def _tokenize(text: str | None) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", (text or "").lower())
    return {word for word in words if word not in DISCOVERY_STOP_WORDS}


def _score_match(grant: dict, organization: Organization | None) -> tuple[float, str]:
    if not organization:
        return 0.0, "No organization profile attached yet."

    org_blob = " ".join(
        filter(
            None,
            [
                organization.name,
                organization.description,
                organization.mission,
                organization.capabilities,
                " ".join(organization.categories or []),
                " ".join(organization.eligibility_tags or []),
            ],
        )
    )
    grant_blob = " ".join(
        filter(
            None,
            [
                grant.get("title"),
                grant.get("description"),
                grant.get("funding_agency"),
                grant.get("category"),
                grant.get("eligibility"),
            ],
        )
    )
    overlap = sorted(_tokenize(org_blob) & _tokenize(grant_blob))
    score = min(len(overlap) * 9, 72)
    if grant.get("source_url"):
        score += 10
    if any(term in grant_blob.lower() for term in ("literacy", "mentoring", "steam", "stem", "summer", "family")):
        score += 12
    score = float(min(score, 100))
    if overlap:
        return score, f"Matched on {', '.join(overlap[:4])}."
    return score, "Source imported successfully; awaiting deeper profile-aligned enrichment."


@router.post("/search", response_model=list[GrantOut])
async def search_grants(
    body: GrantSearch,
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    q = select(Grant)
    if body.query:
        like = f"%{body.query}%"
        q = q.where(or_(
            Grant.title.ilike(like),
            Grant.description.ilike(like),
            Grant.funding_agency.ilike(like),
            Grant.eligibility.ilike(like),
        ))
    if body.category:
        q = q.where(Grant.category.ilike(f"%{body.category}%"))
    if body.status:
        q = q.where(Grant.status == GrantStatus(body.status.value))
    if body.min_amount is not None:
        q = q.where(Grant.amount >= body.min_amount)
    if body.max_amount is not None:
        q = q.where(Grant.amount <= body.max_amount)
    if body.is_renewable is not None:
        q = q.where(Grant.is_renewable == body.is_renewable)
    q = q.order_by(Grant.deadline.asc().nullslast(), Grant.id.asc())
    result = await db.execute(q)
    grants = result.scalars().all()

    return await personalized(db, token, deduplicate(grants)[body.offset:body.offset + body.limit])



@router.get("/", response_model=list[GrantOut])
async def list_grants(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str = "active",
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    q = select(Grant).where(Grant.status == status)
    q = q.order_by(Grant.deadline.asc().nullslast(), Grant.id.asc())
    result = await db.execute(q)
    return await personalized(db, token, deduplicate(result.scalars().all())[offset:offset + limit])


@router.get("/{grant_id}", response_model=GrantOut)
async def get_grant(
    grant_id: int,
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    result = await db.execute(select(Grant).where(Grant.id == grant_id))
    grant = result.scalar_one_or_none()
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")
    return (await personalized(db, token, [grant]))[0]


@router.get("/categories/list")
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    result = await db.execute(
        select(Grant.category, func.count(Grant.id).label("count"))
        .where(Grant.category.isnot(None))
        .group_by(Grant.category)
        .order_by(func.count(Grant.id).desc())
    )
    rows = result.all()
    return [{"category": r.category, "count": r.count} for r in rows]


@router.post("/discover")
async def discover_grants(
    body: dict,
    db: AsyncSession = Depends(get_db),
    token: dict = Depends(get_current_user_token),
):
    query = str(body.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    max_results = max(1, min(int(body.get("max_results") or 20), 50))
    scraper = GrantScraperAgent()
    scraped = await scraper.scrape(query=query, max_results=max_results)

    user_result = await db.execute(select(User).where(User.identity_id == token["identity_id"]).limit(1))
    user = user_result.scalar_one_or_none()
    organization = None
    if user and user.organization_id:
        organization = await db.get(Organization, user.organization_id)

    imported = 0
    updated = 0
    response_items = []

    for item in scraped:
        existing_result = await db.execute(
            select(Grant).where(
                Grant.title == item.get("title"),
                Grant.funding_agency == item.get("funding_agency"),
            ).limit(1)
        )
        existing = existing_result.scalar_one_or_none()
        payload = {
            "description": item.get("description"),
            "amount": item.get("amount"),
            "deadline_str": item.get("deadline_str"),
            "eligibility": item.get("eligibility"),
            "category": item.get("category") or "General",
            "source_url": item.get("source_url"),
            "portal_key": item.get("source"),
            "status": GrantStatus.active,
            "tags": list(sorted(_tokenize(" ".join(filter(None, [item.get("title"), item.get("category"), item.get("funding_agency")])))))[:8],
        }

        if existing:
            for field, value in payload.items():
                setattr(existing, field, value)
            updated += 1
            response_items.append(existing)
            continue

        grant = Grant(
            title=item.get("title") or "Untitled Grant",
            funding_agency=item.get("funding_agency"),
            **payload,
        )
        db.add(grant)
        await db.flush()
        imported += 1
        response_items.append(grant)

    await db.commit()
    from routers.operations import organization_evidence, alignment
    records, documents = await organization_evidence(db, organization.id) if organization else ([], [])
    personalized = []
    for item in response_items:
        result = GrantOut.model_validate(item).model_dump(mode='json')
        match = alignment(organization, item, records, documents) if organization else None
        result['ai_match_score'] = match['score'] if match else None
        result['ai_summary'] = ('Evidence alignment, not award probability. Missing: '+', '.join(match['missing_information'])) if match else 'Assign an organization before matching.'
        personalized.append(result)
    return {
        "success": True,
        "query": query,
        "imported": imported,
        "updated": updated,
        "count": len(response_items),
        "grants": personalized,
    }


# ── Batch requirements scan ────────────────────────────────────────────────────

@router.post("/scan-all-requirements")
async def scan_all_requirements(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Queue requirements scans for all active grants that haven't been scanned yet."""
    result = await db.execute(
        select(Grant).where(
            Grant.status == GrantStatus.active,
            Grant.requirements_fetched_at.is_(None),
        )
    )
    unscanned = result.scalars().all()

    queued_ids = []
    for grant in unscanned:
        status = (grant.meta or {}).get("requirements_status")
        if status == "running":
            continue
        meta = dict(grant.meta or {})
        meta["requirements_status"] = "queued"
        grant.meta = meta
        background_tasks.add_task(_run_requirements_job, grant.id)
        queued_ids.append(grant.id)

    await db.commit()
    return {
        "queued": len(queued_ids),
        "grant_ids": queued_ids,
        "message": f"Queued {len(queued_ids)} grants for requirements scan",
    }


# ── Grant Submission Requirements (OpenClaw scrape) ───────────────────────────

async def _run_requirements_job(grant_id: int):
    """Background job: fetch real submission requirements for a grant via OpenClaw."""
    from automation.agents.grant_requirements import GrantRequirementsAgent
    agent = GrantRequirementsAgent()

    async with AsyncSessionLocal() as db:
        grant = await db.get(Grant, grant_id)
        if not grant:
            return

        # Mark as in-progress in meta
        meta = dict(grant.meta or {})
        meta["requirements_status"] = "running"
        grant.meta = meta
        await db.commit()

        try:
            result = await agent.fetch(
                opp_id=_extract_opp_id(grant.source_url),
                opp_number=_extract_opp_number(grant),
                source_url=grant.source_url,
                grant_title=grant.title,
            )
        except Exception as exc:
            async with AsyncSessionLocal() as db2:
                g2 = await db2.get(Grant, grant_id)
                if g2:
                    m2 = dict(g2.meta or {})
                    m2["requirements_status"] = "error"
                    m2["requirements_error"] = str(exc)
                    g2.meta = m2
                    await db2.commit()
            return

    # Save results
    async with AsyncSessionLocal() as db3:
        g3 = await db3.get(Grant, grant_id)
        if g3:
            m3 = dict(g3.meta or {})
            m3["requirements_status"] = "done" if result.get('success') and not requirement_error(type('Candidate', (), {'requirements_detail':result, 'source_url':g3.source_url})()) else "error"
            m3.pop("requirements_error", None)
            if m3['requirements_status'] == 'error':
                m3['requirements_error'] = result.get('error') or 'No verified package for this opportunity.'
                g3.meta = m3
                await db3.commit()
                return
            g3.meta = m3
            g3.requirements_detail = result
            g3.requirements_fetched_at = datetime.now(timezone.utc)
            # Back-fill eligibility and synopsis if blank
            if not g3.eligibility and result.get("eligibility"):
                g3.eligibility = result["eligibility"][:2000]
            if not g3.description and result.get("synopsis"):
                g3.description = result["synopsis"][:3000]
            await db3.commit()


def _extract_opp_id(url: str | None) -> str | None:
    import re as _re
    if not url:
        return None
    for pat in [r"oppId=(\d+)", r"results-detail\/(\d+)", r"opportunity[_-]?id[=\/](\d+)"]:
        m = _re.search(pat, url or "", _re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _extract_opp_number(grant: Grant) -> str | None:
    # Check tags for opportunity number (e.g. "HHS-2024-ACF-ANA-NA-0013")
    for tag in (grant.tags or []):
        if tag and len(tag) > 8 and "-" in tag:
            return tag
    return None


@router.post("/{grant_id}/requirements")
async def fetch_grant_requirements(
    grant_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Trigger OpenClaw scrape to discover real submission requirements for this grant."""
    grant = await db.get(Grant, grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")

    if not opportunity_id(grant.source_url):
        raise HTTPException(422, 'No exact Grants.gov opportunity ID is available for this funder source. Open the original funder page; a keyword search cannot verify its requirements.')
    status = (grant.meta or {}).get("requirements_status")
    if status == "running":
        return {"status": "running", "message": "Requirements fetch already in progress"}

    background_tasks.add_task(_run_requirements_job, grant_id)
    return {
        "status": "queued",
        "grant_id": grant_id,
        "message": "Fetching submission requirements from grants.gov — check back in 15–30 seconds",
    }


@router.get("/{grant_id}/requirements")
async def get_grant_requirements(
    grant_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user_token),
):
    """Return the scraped submission requirements for this grant."""
    grant = await db.get(Grant, grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")

    status = (grant.meta or {}).get("requirements_status", "none")
    return {
        "grant_id": grant_id,
        "status": "error" if requirement_error(grant) else status,
        "fetched_at": grant.requirements_fetched_at.isoformat() if grant.requirements_fetched_at else None,
        "requirements": safe_requirements(grant),
        "error": requirement_error(grant) or (grant.meta or {}).get("requirements_error"),
    }
