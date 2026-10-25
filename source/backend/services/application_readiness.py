"""Explainable checks over saved application state; never submits to a funder."""
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import select
from models.models import Grant, Organization, Review, OrganizationRecord, Document, IngestionDocument
from services.ingestion_review import freshness


def draft_revision(app):
    fields={key:getattr(app,key) for key in ('proposal_text','budget_narrative','amount_requested','form_data','grant_id','organization_id')}
    return hashlib.sha256(json.dumps(fields,sort_keys=True,default=str).encode()).hexdigest()


async def latest_acceptance(db,app):
    review=(await db.execute(select(Review).where(Review.application_id==app.id).order_by(Review.id.desc()))).scalars().first()
    valid=bool(review and review.status=='accepted' and (review.criteria or {}).get('application_revision')==draft_revision(app))
    return review,valid


async def readiness(db,app):
    grant=await db.get(Grant,app.grant_id)
    org=await db.get(Organization,app.organization_id) if app.organization_id else None
    records=(await db.execute(select(OrganizationRecord).where(OrganizationRecord.organization_id==app.organization_id))).scalars().all()
    checks=[]
    def add(key,label,passed,detail):checks.append({'key':key,'label':label,'passed':bool(passed),'detail':detail})
    add('opportunity','Opportunity active',grant and getattr(grant.status,'value',grant.status)=='active','Confirm that the funder is still accepting applications.')
    add('mission','Organizational mission',org and (org.mission or '').strip(),'Save the organization mission to ground matching and drafting.')
    add('proposal','Saved proposal',bool((app.proposal_text or '').strip()),'Save the narrative before requesting review.')
    add('budget','Saved budget narrative',bool((app.budget_narrative or '').strip()),'Explain the requested costs and funding use.')
    valid_amount=app.amount_requested is not None and app.amount_requested>0
    add('amount','Requested amount',valid_amount,'A positive requested amount is needed for the budget review.')
    if grant and grant.amount_max is not None:
        add('ceiling','Funding ceiling',valid_amount and app.amount_requested<=grant.amount_max,f'Published ceiling: {grant.amount_max}; requested: {app.amount_requested}. Confirm currency and current funder rules.')
    if grant and grant.deadline:
        deadline=grant.deadline.replace(tzinfo=timezone.utc) if grant.deadline.tzinfo is None else grant.deadline
        add('deadline','Application deadline',deadline>=datetime.now(timezone.utc),f'Saved deadline: {deadline.isoformat()}. Verify against the funder source.')
    else:add('deadline','Application deadline confirmed',False,'No structured deadline is saved. Confirm rolling applications or the actual due date.')
    requirements=[]
    for requirement in (grant.requirements or []) if grant else []:
        label=requirement if isinstance(requirement,str) else requirement.get('name') or requirement.get('title') if isinstance(requirement,dict) else None
        if label:requirements.append(label)
    if grant:
        detail=grant.requirements_detail if isinstance(grant.requirements_detail,dict) else {}
        for form in (detail.get('required_forms') or [])+(detail.get('required_attachments') or []):
            if isinstance(form,dict) and form.get('is_mandatory') and form.get('name'):requirements.append(form['name'])
    accepted_checklist={str(c.get('label','')).strip().casefold():{'record_id':r.id,'revision':r.revision,'evidence':c['evidence'],'owner':c['owner']}
        for r in records if r.kind=='audit' and r.data.get('application_id')==app.id and r.data.get('status')=='accepted'
        and (not r.data.get('due_date') or r.data['due_date']>=datetime.now(timezone.utc).date().isoformat())
        for c in r.data.get('checklist',[]) if c.get('done') and c.get('evidence') and c.get('owner')}
    add('requirements_known','Funder requirements available',bool(requirements),'Saved requirements are a checklist, not proof that the funder package is complete.')
    for index,label in enumerate(dict.fromkeys(requirements)):
        evidence=accepted_checklist.get(label.strip().casefold())
        add(f'requirement_{index}',label,bool(evidence),evidence or 'Record an accepted application audit checklist item with this label, evidence and owner in Organization Workspace.')
    eligibility=[r for r in records if r.kind=='knowledge' and r.data.get('grant_id')==app.grant_id and r.data.get('category')=='eligibility_review' and r.data.get('status')=='accepted' and r.data.get('evidence_match') and r.data.get('source_url') and (not r.data.get('due_date') or r.data['due_date']>=datetime.now(timezone.utc).date().isoformat())]
    add('eligibility','Sourced eligibility review',bool(eligibility),'A reviewer must confirm eligibility using the funder source; keyword similarity is not eligibility.')
    review,valid=await latest_acceptance(db,app)
    add('acceptance','Current application accepted',valid,'Acceptance covers saved proposal, budget, amount and form answers. Changes require a new review.')
    docs=(await db.execute(select(IngestionDocument,Document).join(Document,Document.id==IngestionDocument.document_id).where(
        IngestionDocument.organization_id==app.organization_id,IngestionDocument.current==True,IngestionDocument.status!='deleted',
        (Document.application_id==app.id)|(Document.application_id.is_(None))))).all()
    warnings=[]
    from decimal import Decimal, InvalidOperation
    total=(((app.form_data or {}).get('grant_planning') or {}).get('summary') or {}).get('budget_total')
    if total is not None and app.amount_requested is not None:
        try:
            if Decimal(str(total))!=Decimal(str(app.amount_requested)):
                warnings.append(f'Budget total {total} differs from requested funding {app.amount_requested}. Review cost sharing or reconcile the figures; this difference is not automatically an error.')
        except InvalidOperation:warnings.append('Saved budget total is not a valid number; review the planning data.')
    if any(i.status!='ready' for i,d in docs):warnings.append('Some associated evidence is still processing, failed, or awaiting extraction approval.')
    if any(freshness(i)['stale'] for i,d in docs):warnings.append('Associated evidence is overdue for review; confirm that figures are still current.')
    return {'application_id':app.id,'revision':draft_revision(app),'ready':all(c['passed'] for c in checks) and not warnings,
        'review_snapshot':{'proposal_text':app.proposal_text or '', 'budget_narrative':app.budget_narrative or '',
                           'amount_requested':app.amount_requested,'form_data':app.form_data or {}},
        'checks':checks,'completed':sum(c['passed'] for c in checks),'total':len(checks),'warnings':warnings,
        'latest_review':{'status':review.status,'feedback':review.feedback,'reviewer_id':review.reviewer_id,'current':valid} if review else None,
        'note':'Advisory readiness based on saved data. Human approval and funder validation remain required; nothing is submitted automatically.'}
