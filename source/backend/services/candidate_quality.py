"""Shared save/acceptance checks; source warnings never prevent drafting."""
from fastapi import HTTPException
from sqlalchemy import select
from models.models import Grant, Document, OrganizationRecord
from services.draft_validation import draft_issues
from services.grant_integrity import requirement_error, source_review


async def context_for(db, application):
    sources=[]
    if application and application.organization_id:
        from models.models import IngestionDocument
        rows=(await db.execute(select(Document,IngestionDocument).join(IngestionDocument,IngestionDocument.document_id==Document.id).where(
            IngestionDocument.organization_id==application.organization_id,IngestionDocument.current==True,IngestionDocument.status=='ready',
            (Document.application_id==application.id)|(Document.application_id.is_(None))))).all()
        sources += [{'title':f'{doc.original_filename or doc.filename} [document {doc.id} v{item.version}]','excerpt':doc.extracted_text or ''} for doc,item in rows]
        records=(await db.execute(select(OrganizationRecord).where(OrganizationRecord.organization_id==application.organization_id,OrganizationRecord.kind=='knowledge'))).scalars().all()
        sources += [{'title':f'{r.title} [record {r.id}, revision {r.revision}]','excerpt':r.body} for r in records if r.data.get('status')=='accepted']
    return {'application':{'amount_requested':application.amount_requested if application else None},'knowledge_documents':sources}


async def assess(db, application, body, category='proposal'):
    context=await context_for(db,application)
    # Arbitrary workspace categories must not disable financial/evidence checks.
    issues=draft_issues(body,context,category if category in {'proposal','budget','loi','renewal'} else 'proposal')
    warnings=[]
    grant=await db.get(Grant,application.grant_id) if application else None
    if not grant or requirement_error(grant) or (not source_review(grant) and not grant.requirements_detail):
        warnings.append('Needs source verification: confirm the opportunity requirements before asserting compliance or submission readiness.')
    return {'issues':issues,'warnings':warnings,'status':'needs_review' if issues or warnings else 'content_checks_passed',
            'note':'Automated checks do not certify evidence truth, eligibility or readiness to submit.'}


async def require_valid_content(db, application, body, category='proposal', *, acceptance=False):
    quality=await assess(db,application,body,category)
    if quality['issues'] or (acceptance and quality['warnings']):
        raise HTTPException(422,'Draft requires correction or source verification. '+ ' '.join(quality['issues']+quality['warnings'])+' Existing saved text is unchanged.')
    return quality
