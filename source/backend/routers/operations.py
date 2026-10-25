"""Organization-scoped COYF knowledge and delivery records; no external submissions."""
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from auth.jwt_handler import get_current_user_token
from models.models import Organization, OrganizationRecord, User, Grant, GrantApplication, AuditLog, Document

router = APIRouter(prefix='/api/operations', tags=['organization operations'])
Kind = Literal['knowledge', 'partnership', 'audit', 'configuration', 'draft']


@router.get('/next-actions')
async def next_actions(db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    user, org = await scope(db, token)
    apps = (await db.execute(select(GrantApplication).where(GrantApplication.organization_id == org.id))).scalars().all()
    rows = (await db.execute(select(OrganizationRecord).where(OrganizationRecord.organization_id == org.id))).scalars().all()
    items = []
    grants={g.id:g for g in (await db.execute(select(Grant).where(Grant.id.in_([a.grant_id for a in apps])))).scalars().all()}
    for app in apps:
        status = app.status.value
        if status in ('draft', 'in_review', 'renewal_due'):
            items.append({'title':app.title or f'Application {app.id}', 'reason':{'draft':'Continue drafting','in_review':'Human review required','renewal_due':'Prepare renewal draft'}[status],
                          'href':f'/applications/{app.id}', 'due':(app.renewal_due_date.isoformat() if app.renewal_due_date else None) if status=='renewal_due' else
                          (grants[app.grant_id].deadline.isoformat() if app.grant_id in grants and grants[app.grant_id].deadline else None)})
        for report in app.report_due_dates or []:
            if isinstance(report,dict) and report.get('status') != 'completed':
                items.append({'title':report.get('label') or 'Grant report', 'reason':'Reporting deadline', 'href':f'/applications/{app.id}', 'due':report.get('date')})
    for row in rows:
        if row.data.get('status') not in ('closed','accepted') and (row.data.get('due_date') or row.data.get('next_step')):
            items.append({'title':row.title, 'reason':row.data.get('next_step') or 'Review workspace record', 'href':'/operations','due':row.data.get('due_date')})
    config = next((r for r in rows if r.kind == 'configuration'), None)
    limit = config.data.get('dashboard_limit', 12) if config else 12
    return sorted(items, key=lambda x:x['due'] or '9999')[:limit]


class ChecklistItem(BaseModel):
    label: str = Field(min_length=1, max_length=500)
    done: bool = False
    evidence: str = Field(default='', max_length=4000)
    owner: str = Field(default='', max_length=255)


class RecordInput(BaseModel):
    kind: Kind
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(default='', max_length=100000)
    revision: int = Field(default=0, ge=0)
    category: str = Field(default='', max_length=100)
    source_url: str = Field(default='', max_length=2000)
    contact: str = Field(default='', max_length=500)
    status: Literal['open', 'active', 'review', 'accepted', 'closed'] = 'open'
    owner: str = Field(default='', max_length=255)
    next_step: str = Field(default='', max_length=4000)
    due_date: str = Field(default='', max_length=10)
    grant_id: int | None = None
    application_id: int | None = None
    priorities: str = Field(default='', max_length=2000)
    funding_min: float = Field(default=0, ge=0)
    funding_max: float = Field(default=0, ge=0)
    stages: str = Field(default='', max_length=2000)
    approval_role: Literal['reviewer', 'admin'] = 'reviewer'
    dashboard_limit: int = Field(default=12, ge=1, le=30)
    auto_renew: bool = False
    renewal_lead_days: int = Field(default=30, ge=1, le=90)
    custom_field_names: str = Field(default='', max_length=2000)
    custom_values: dict[str, str] = Field(default_factory=dict)
    checklist: list[ChecklistItem] = Field(default_factory=list, max_length=100)
    evidence_match: bool = False


async def scope(db, token):
    user = (await db.execute(select(User).where(User.identity_id == token['identity_id']))).scalar_one_or_none()
    if not user or not user.organization_id:
        raise HTTPException(409, 'Assign an organization in the existing account setup before using this workspace.')
    org = await db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(404, 'Organization not found')
    return user, org


def output(row):
    return {'id': row.id, 'kind': row.kind, 'title': row.title, 'body': row.body,
            'revision': row.revision, 'data': row.data, 'history': row.history,
            'organization_id': row.organization_id}


@router.get('/records')
async def records(kind: Kind | None = None, db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    _, org = await scope(db, token)
    q = select(OrganizationRecord).where(OrganizationRecord.organization_id == org.id,
        OrganizationRecord.kind != 'alignment_run')
    if kind:
        q = q.where(OrganizationRecord.kind == kind)
    rows = (await db.execute(q.order_by(OrganizationRecord.id.desc()))).scalars().all()
    return [output(row) for row in rows]


@router.post('/knowledge/upload', status_code=202)
async def upload_knowledge(file: UploadFile = File(...), category: str = Form(''),
                           db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    from routers.ingestion import upload
    aliases={'financial':'financials','audit':'audits','budget':'financials','990':'financials','mission_statement':'mission'}
    category=aliases.get(category,category) or 'general'
    return await upload(file=file,category=category,application_id=None,grant_id=None,db=db,token=token)


@router.post('/records', status_code=201)
@router.put('/records/{record_id}')
async def save_record(payload: RecordInput, record_id: int | None = None,
                      db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    user, org = await scope(db, token)
    if token.get('role') == 'viewer':
        raise HTTPException(403, 'Read-only account')
    if any(item.done and (not item.evidence.strip() or not item.owner.strip()) for item in payload.checklist):
        raise HTTPException(422, 'Completed checklist items require evidence and an owner')
    if payload.evidence_match:
        if token.get('role') not in ('admin','reviewer'):
            raise HTTPException(403, 'Reviewer or administrator required to confirm evidence alignment')
        if payload.kind != 'knowledge' or payload.category not in ('eligibility_review','award_history') or not payload.grant_id or not payload.source_url or not payload.body.strip() or payload.status != 'accepted':
            raise HTTPException(422, 'Confirmed evidence requires an accepted knowledge record, grant, source URL, explanation and eligibility_review or award_history category')
    if payload.kind == 'configuration' and token.get('role') != 'admin':
        raise HTTPException(403, 'Administrator required to configure the organization')
    if payload.kind == 'configuration' and not record_id:
        existing = (await db.execute(select(OrganizationRecord.id).where(OrganizationRecord.organization_id == org.id,
                    OrganizationRecord.kind == 'configuration'))).scalars().first()
        if existing:
            raise HTTPException(409, 'Edit the existing organization configuration instead of creating another')
    if len(payload.custom_values)>30 or any(len(k)>100 or len(v)>2000 for k,v in payload.custom_values.items()):
        raise HTTPException(422, 'Use at most 30 custom fields, with names under 100 and values under 2000 characters')
    if payload.status == 'accepted' and token.get('role') not in ('admin', 'reviewer'):
        raise HTTPException(403, 'A reviewer or administrator must accept deliverables')
    if payload.funding_max and payload.funding_max < payload.funding_min:
        raise HTTPException(422, 'Maximum funding must be at least the minimum')
    if payload.source_url and not payload.source_url.startswith(('https://', 'http://')):
        raise HTTPException(422, 'Source must be an HTTP or HTTPS URL')
    if payload.due_date:
        try:
            datetime.strptime(payload.due_date, '%Y-%m-%d')
        except ValueError:
            raise HTTPException(422, 'Due date must be YYYY-MM-DD')
    if payload.grant_id and not await db.get(Grant, payload.grant_id):
        raise HTTPException(404, 'Grant not found')
    if payload.application_id:
        app = await db.get(GrantApplication, payload.application_id)
        if not app or app.organization_id != org.id:
            raise HTTPException(404, 'Application not found')
    row = None
    if record_id:
        row = (await db.execute(select(OrganizationRecord).where(
            OrganizationRecord.id == record_id, OrganizationRecord.organization_id == org.id))).scalar_one_or_none()
        if not row:
            raise HTTPException(404, 'Record not found')
        if row.revision != payload.revision:
            raise HTTPException(409, 'Record changed. Reload before saving.')
        if row.kind != payload.kind:
            raise HTTPException(422, 'Record type cannot change')
    elif payload.revision:
        raise HTTPException(409, 'New records start at revision zero')
    data = payload.model_dump(exclude={'kind', 'title', 'body', 'revision'})
    event = {'actor': token['username'], 'at': datetime.now(timezone.utc).isoformat(),
             'revision': (row.revision + 1) if row else 1, 'title': payload.title,
             'body': payload.body, 'data': data,
             'sha256': hashlib.sha256(payload.body.encode()).hexdigest()}
    if row:
        row.title, row.body, row.data = payload.title, payload.body, data
        row.revision += 1
        row.history = (row.history or []) + [event]
    else:
        row = OrganizationRecord(organization_id=org.id, created_by_id=user.id,
            kind=payload.kind, title=payload.title, body=payload.body, data=data, revision=1, history=[event])
        db.add(row)
    from sqlalchemy.orm.exc import StaleDataError
    try:
        await db.flush()
    except StaleDataError:
        await db.rollback()
        raise HTTPException(409, 'Record changed. Reload before saving.')
    db.add(AuditLog(user_id=user.id, action='organization_record_saved', resource_type=payload.kind,
                    resource_id=row.id, details={'revision': row.revision, 'organization_id': org.id}))
    await db.flush()
    return output(row)


@router.get('/records/{record_id}/export', response_class=PlainTextResponse)
async def export_record(record_id: int, db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    _, org = await scope(db, token)
    row = (await db.execute(select(OrganizationRecord).where(OrganizationRecord.id == record_id,
                           OrganizationRecord.organization_id == org.id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, 'Record not found')
    return PlainTextResponse(row.title + '\n\n' + row.body + '\n\nRecord details:\n' + json.dumps(row.data, indent=2),
        headers={'Content-Disposition': f'attachment; filename="grantflow-record-{row.id}-v{row.revision}.txt"'})


def words(text):
    return set(re.findall(r'[a-z]{4,}', (text or '').lower())) - {'with', 'that', 'this', 'from', 'their', 'will', 'have'}


async def organization_evidence(db, org_id):
    records = (await db.execute(select(OrganizationRecord).where(
        OrganizationRecord.organization_id == org_id,
        OrganizationRecord.kind.in_(['knowledge', 'configuration', 'audit', 'partnership'])
    ).order_by(OrganizationRecord.id.desc()))).scalars().all()
    documents = (await db.execute(select(Document).where(Document.organization_id == org_id)
        .order_by(Document.id.desc()))).scalars().all()
    from models.models import IngestionDocument
    ingested=(await db.execute(select(IngestionDocument).where(IngestionDocument.organization_id==org_id))).scalars().all()
    excluded={i.document_id for i in ingested if i.status!='ready' or not i.current}
    documents=[d for d in documents if d.id not in excluded]
    active={i.document_id:i for i in ingested if i.current and i.status=='ready'}
    for doc in documents:
        item=active.get(doc.id)
        if item:
            from services.ingestion_review import freshness
            dates=freshness(item)
            doc.ingestion_citation={'revision':item.version,'source_url':f'/gfm-app/documents?document={item.id}',
                'ingestion_id':item.id,'review_due':dates['review_due'],
                'needs_review':dates['stale'],'evidence_date':dates['as_of']}
    return records, documents


def knowledge_summary(org, records, documents):
    """Read current source revisions on every request; never treat AI drafts as evidence."""
    today = datetime.now(timezone.utc).date().isoformat()
    sources = [{'id':r.id, 'type':r.kind, 'title':r.title, 'revision':r.revision,
                'category':r.data.get('category',''), 'source_url':r.data.get('source_url',''),
                'review_due':r.data.get('due_date') or None,
                'needs_review':bool(r.data.get('due_date') and r.data['due_date'] < today)}
               for r in records if r.kind != 'configuration']
    sources += [{'id':d.id, 'type':'document', 'title':d.original_filename or d.filename,
                 'category':d.document_type or '', 'revision':None, 'needs_review':False,
                 'updated_at':str(d.updated_at or d.created_at),**getattr(d,'ingestion_citation',{})} for d in documents]
    present = {r.data.get('category','').lower() for r in records if r.kind=='knowledge' and r.body.strip()}
    present |= {(d.document_type or '').lower() for d in documents if d.extracted_text or d.ai_summary}
    aliases = {'financials':{'financials','financial','budget','990'}, 'mission':{'mission','mission_statement'},
               'priorities':{'priorities'}, 'successful_grants':{'successful_grants'},
               'audits':{'audit','audits'}, 'award_history':{'award_history'}}
    if org.mission: present.add('mission')
    if any(r.kind=='configuration' and r.data.get('priorities') for r in records): present.add('priorities')
    if any(r.kind=='audit' and (r.body.strip() or r.data.get('checklist')) for r in records): present.add('audits')
    missing = [name for name, values in aliases.items() if not values & present]
    fingerprint_data = {'profile':{'mission':org.mission,'description':org.description,
        'capabilities':org.capabilities,'categories':org.categories,'eligibility_tags':org.eligibility_tags,'meta':org.meta},
        'records':[(r.id,r.revision,r.body,r.data) for r in records],
        'documents':[(d.id,d.extracted_text,d.ai_summary,str(d.updated_at),getattr(d,'ingestion_citation',{})) for d in documents]}
    return {'refreshed_at':datetime.now(timezone.utc).isoformat(), 'refresh_policy':'Read from current persisted sources on every request',
        'fingerprint':hashlib.sha256(json.dumps(fingerprint_data,sort_keys=True,default=str).encode()).hexdigest(),
        'sources':sources, 'missing_categories':missing,
        'recommendations':[{'category':name,'reason':'No readable source currently available. Add and review this evidence before using it in a draft.'} for name in missing],
        'note':'Source presence is not verification. Review financials and outcomes before approval. Authorized document folders can be refreshed by the ingestion worker; review-required extractions are withheld from AI evidence.'}


@router.get('/knowledge-status')
async def knowledge_status(db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    _, org = await scope(db, token)
    records, documents = await organization_evidence(db, org.id)
    return knowledge_summary(org, records, documents)


class DraftRequest(BaseModel):
    application_id: int
    task: Literal['loi', 'proposal', 'budget'] = 'loi'


@router.post('/drafts', status_code=201)
async def draft(payload: DraftRequest, db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    _, org = await scope(db, token)
    app = await db.get(GrantApplication, payload.application_id)
    if not app or app.organization_id != org.id:
        raise HTTPException(404, 'Application not found')
    from routers.ai_router import _build_rag_context, _ai
    from services.ai_service import AIUnavailable
    context = await _build_rag_context(db, token, application_id=app.id, grant_id=app.grant_id)
    try:
        body = await _ai.generate(payload.task, context)
    except AIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    saved = await save_record(RecordInput(kind='draft', title=f'{payload.task.upper()}: {app.title or app.id}',
        body=body, category=payload.task, application_id=app.id, grant_id=app.grant_id,
        next_step='Review all facts and evidence before requesting human approval.'), None, db, token)
    from services.document_ingestion import record_use
    await record_use(db,context.get('ingestion_ids',[]),org.id,'record',saved['id'],'body')
    await db.commit()
    return saved


def alignment(org, grant, records, documents=()):
    """Transparent lexical evidence score, explicitly not a funding probability."""
    config = next((r.data for r in records if r.kind == 'configuration'), {}) or {}
    today=datetime.now(timezone.utc).date().isoformat()
    knowledge = [r for r in records if r.kind == 'knowledge' and r.data.get('status')!='closed']
    current_knowledge=[r for r in knowledge if not r.data.get('due_date') or r.data['due_date']>=today]
    current_documents=[d for d in documents if not getattr(d,'ingestion_citation',{}).get('needs_review')]
    grant_words = words(' '.join([grant.title or '', grant.description or '', grant.category or '']))
    factors = []
    for label, text, weight in [('Mission', org.mission, 20),
                              ('Profile', ' '.join([org.description or '', org.capabilities or '', ' '.join(org.eligibility_tags or [])]), 10),
                              ('Priorities', config.get('priorities') or ' '.join(org.categories or []), 25),
                              ('Knowledge evidence', ' '.join([r.body for r in current_knowledge]+[d.extracted_text or d.ai_summary or '' for d in current_documents]), 15)]:
        terms = words(text)
        matches = sorted(terms & grant_words)
        factors.append({'name': label, 'weight': weight, 'score': round(weight * min(1, len(matches)/max(1,min(len(terms),5))),1),
                        'evidence': matches, 'missing': not bool(terms)})
    lo, hi = config.get('funding_min', 0), config.get('funding_max', 0)
    amount = grant.amount_max or grant.amount
    known = bool(amount is not None and (lo or hi))
    # A ceiling above the organization's target does not rule out a smaller request.
    fits = known and amount >= lo and (grant.amount_max is not None or not hi or amount <= hi)
    factors.append({'name':'Funding scale', 'weight':15, 'score':15 if fits else 0,
                    'evidence': {'grant_amount': amount, 'minimum':lo, 'maximum':hi,
                        'basis':'Ceiling compatibility only; minimum award and funder terms need verification' if grant.amount_max is not None else 'Published amount'}, 'missing':not known})
    # Only explicit, sourced human reviews contribute these factors. Keyword overlap is insufficient.
    for label, category, weight in [('Eligibility review','eligibility_review',10), ('Previous awardee evidence','award_history',5)]:
        evidence = [{'record_id':r.id,'revision':r.revision,'source_url':r.data['source_url'],'explanation':r.body}
                    for r in current_knowledge if r.data.get('category')==category and r.data.get('grant_id')==grant.id
                    and r.data.get('status')=='accepted' and r.data.get('evidence_match') and r.data.get('source_url')]
        factors.append({'name':label,'weight':weight,'score':weight if evidence else 0,'evidence':evidence,'missing':not bool(evidence)})
    return {'grant_id':grant.id, 'title':grant.title, 'score':round(sum(f['score'] for f in factors),1),
            'score_type':'Evidence alignment, not probability of award', 'scoring_version':'coyf-lexical-v4',
            'warnings':(['Overdue evidence is listed for traceability but excluded from scoring.'] if len(current_documents)!=len(documents) or len(current_knowledge)!=len(knowledge) else []),
            'factors':factors, 'missing_information':[f['name'] for f in factors if f['missing']],
            'source_url':grant.source_url, 'documents':[{'id':r.id,'type':'knowledge','title':r.title,'revision':r.revision,'source_url':r.data.get('source_url')} for r in knowledge]+
                [{'id':d.id,'type':'document','title':d.original_filename or d.filename,'revision':None,**getattr(d,'ingestion_citation',{})} for d in documents]}


@router.get('/alignment')
async def align(db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    _, org = await scope(db, token)
    rows, documents = await organization_evidence(db, org.id)
    grants = (await db.execute(select(Grant).where(Grant.status == 'active').order_by(Grant.id.desc()).limit(200))).scalars().all()
    return sorted([alignment(org,g,rows,documents) for g in grants], key=lambda x:x['score'], reverse=True)


@router.get('/alignment-runs')
async def alignment_runs(db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    _, org = await scope(db, token)
    rows = (await db.execute(select(OrganizationRecord).where(OrganizationRecord.organization_id == org.id,
        OrganizationRecord.kind == 'alignment_run').order_by(OrganizationRecord.id.desc()).limit(30))).scalars().all()
    return [output(row) for row in rows]


@router.post('/alignment-runs', status_code=201)
async def save_alignment_run(db: AsyncSession = Depends(get_db), token: dict = Depends(get_current_user_token)):
    user, org = await scope(db, token)
    if token.get('role') == 'viewer':
        raise HTTPException(403, 'Read-only account')
    matches = await align(db, token)
    profile = {'mission':org.mission, 'categories':org.categories, 'description':org.description,
               'capabilities':org.capabilities,'eligibility_tags':org.eligibility_tags}
    rows, documents = await organization_evidence(db, org.id)
    source_state = knowledge_summary(org, rows, documents)
    at = datetime.now(timezone.utc).isoformat()
    row = OrganizationRecord(organization_id=org.id, created_by_id=user.id, kind='alignment_run',
        title=f'Alignment evaluation {at}', body='', revision=1,
        data={'matches':matches, 'profile':profile,
              'profile_fingerprint':source_state['fingerprint'], 'sources':source_state['sources'],
              'at':at, 'feedback':[]},
        history=[{'actor':token['username'],'at':at,'revision':1,'action':'alignment_saved'}])
    db.add(row)
    await db.flush()
    from models.models import IngestionDocument
    from services.document_ingestion import record_use
    ingestion_ids=(await db.execute(select(IngestionDocument.id).where(IngestionDocument.organization_id==org.id,
        IngestionDocument.document_id.in_([d.id for d in documents]),IngestionDocument.current==True,IngestionDocument.status=='ready'))).scalars().all()
    await record_use(db,ingestion_ids,org.id,'record',row.id,'body')
    db.add(AuditLog(user_id=user.id,action='alignment_saved',resource_type='alignment_run',resource_id=row.id,
                    details={'organization_id':org.id,'grant_count':len(matches)}))
    await db.commit()
    return output(row)


class AlignmentFeedback(BaseModel):
    grant_id: int
    useful: bool
    reason: str = Field(min_length=1, max_length=2000)
    revision: int = Field(ge=1)


@router.post('/alignment-runs/{run_id}/feedback')
async def alignment_feedback(run_id: int, payload: AlignmentFeedback, db: AsyncSession = Depends(get_db),
                             token: dict = Depends(get_current_user_token)):
    user, org = await scope(db, token)
    if token.get('role') == 'viewer':
        raise HTTPException(403, 'Read-only account')
    row = (await db.execute(select(OrganizationRecord).where(OrganizationRecord.id==run_id,
        OrganizationRecord.organization_id==org.id, OrganizationRecord.kind=='alignment_run'))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, 'Evaluation not found')
    if row.revision != payload.revision:
        raise HTTPException(409, 'Evaluation changed. Reload before adding feedback.')
    if not any(m['grant_id']==payload.grant_id for m in row.data['matches']):
        raise HTTPException(422, 'Grant is not in this evaluation')
    event = {**payload.model_dump(exclude={'revision'}),'actor':token['username'],
             'at':datetime.now(timezone.utc).isoformat(),'revision':row.revision+1}
    row.data = {**row.data,'feedback':row.data.get('feedback',[])+[event]}
    row.history = row.history+[event]
    row.revision += 1
    db.add(AuditLog(user_id=user.id,action='alignment_feedback',resource_type='alignment_run',resource_id=row.id,details=event))
    from sqlalchemy.orm.exc import StaleDataError
    try:
        await db.commit()
    except StaleDataError:
        await db.rollback()
        raise HTTPException(409, 'Evaluation changed. Reload before adding feedback.')
    return output(row)
