"""Application-source workflow API: all records are tenant and application scoped."""
import json
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import Response
from pydantic import BaseModel,Field
from sqlalchemy import select,update
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from auth.jwt_handler import get_current_user_token
from models.models import (GrantApplication,ApplicationSourceRun as Run,ApplicationSourceReview as Review,
    IngestionDocument,Document)
from routers.operations import scope
from services import application_sources as service

router=APIRouter(prefix='/api/applications/{app_id}/sources',tags=['application source workflow'])

async def application(db,token,id,write=False):
    user,org=await scope(db,token)
    app=await db.get(GrantApplication,id)
    if not app or app.organization_id!=org.id:raise HTTPException(404,'Application not found')
    if write and token.get('role')=='viewer':raise HTTPException(403,'Read-only account')
    return app,user

async def run_for(db,app,id):
    run=await db.get(Run,id)
    if not run or run.organization_id!=app.organization_id or run.application_id!=app.id:raise HTTPException(404,'Run not found')
    return run

async def fresh(db,run):
    try:await service.current_sources(db,run)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc

class Analyze(BaseModel):
    source_ids:list[int]=Field(min_length=1,max_length=30)
    authorities:dict[str,str]=Field(default_factory=dict)

@router.get('')
async def state(app_id:int,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    app,_=await application(db,token,app_id)
    return {'runs':await service.status(db,app),'role':token['role'],'submission_ready':False,
        'note':'Onboarding completeness, submission readiness and competitiveness are separate. Nothing is submitted automatically.'}

@router.post('/analyze',status_code=202)
async def analyze(app_id:int,payload:Analyze,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    app,user=await application(db,token,app_id,True)
    sources=await service.source_snapshot(db,app,payload.source_ids,payload.authorities)
    run=await service.enqueue(db,app,user.id,'inventory',{},sources)
    for ref in sources:
        item=await db.get(IngestionDocument,ref['id'])
        if item.error and item.error.startswith('Extraction succeeded; automatic AI analysis'):item.error=None
    await db.commit()
    return {'id':run.id,'status':run.status}

class Match(BaseModel):
    inventory_id:int
    evidence_ids:list[int]=Field(default_factory=list,max_length=30)

@router.post('/match',status_code=202)
async def match(app_id:int,payload:Match,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    app,user=await application(db,token,app_id,True);parent=await run_for(db,app,payload.inventory_id)
    if parent.kind!='inventory' or parent.status!='completed':raise HTTPException(409,'Completed inventory required')
    await fresh(db,parent)
    refs=await service.source_snapshot(db,app,payload.evidence_ids,{str(i):'organization_evidence' for i in payload.evidence_ids})
    run=await service.enqueue(db,app,user.id,'match',{'inventory_id':parent.id},refs)
    return {'id':run.id,'status':run.status}

class Draft(Match):
    requirement_id:str=Field(min_length=1,max_length=100)
    document_type:Literal['answer','narrative','budget_narrative','work_plan','evaluation_plan']='answer'
    missing_inputs:str=Field(default='',max_length=4000)
    revises:int|None=None

@router.post('/draft',status_code=202)
async def draft(app_id:int,payload:Draft,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    app,user=await application(db,token,app_id,True);parent=await run_for(db,app,payload.inventory_id)
    if parent.kind!='inventory' or parent.status!='completed':raise HTTPException(409,'Completed inventory required')
    await fresh(db,parent)
    req=next((r for r in parent.output['items'] if r['id']==payload.requirement_id),None)
    decisions=await service.latest_reviews(db,parent)
    if decisions.get(payload.requirement_id,{}).get('decision')=='rejected':raise HTTPException(422,'This requirement was excluded by reviewer decision. Review its applicability before drafting.')
    if not req or not service.draftable(req):raise HTTPException(422,'A person must supply this item or confirm it in the portal; select a draftable answer/narrative/work-plan requirement.')
    if payload.revises is not None:
        previous=await run_for(db,app,payload.revises)
        if previous.kind!='draft' or previous.status!='completed' or previous.inputs.get('inventory_id')!=parent.id or previous.inputs.get('requirement_id')!=req['id'] or previous.output.get('document_type')!=payload.document_type:
            raise HTTPException(409,'Select a completed draft of this requirement and document type; previous work is retained.')
        await fresh(db,previous)
    evidence=await service.source_snapshot(db,app,payload.evidence_ids,{str(i):'organization_evidence' for i in payload.evidence_ids})
    refs={r['id']:r for r in parent.sources}
    refs.update({r['id']:r for r in evidence})
    run=await service.enqueue(db,app,user.id,'draft',payload.model_dump(),list(refs.values()))
    return {'id':run.id,'status':run.status}

class RetryRequest(BaseModel):
    reason:str=Field(default='',max_length=1000)

@router.post('/runs/{id}/retry',status_code=202)
async def retry(app_id:int,id:int,payload:RetryRequest|None=None,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    app,user=await application(db,token,app_id,True);run=await run_for(db,app,id)
    if run.status=='completed' and run.kind=='inventory' and run.output.get('withheld_batches'):
        await fresh(db,run)
        recovery=await service.enqueue(db,app,user.id,'inventory',{**run.inputs,'revises':run.id,'retry_withheld':True},run.sources)
        if recovery.status=='queued' and not recovery.output:
            bad={r['batch'] for r in run.output['withheld_batches']}
            checkpoint=run.output.get('checkpoint',{})
            recovery.output={'checkpoint':{**checkpoint,'completed_batches':[i for i in checkpoint.get('completed_batches',[]) if i not in bad],'withheld':[]},
                             'checkpoint_from':run.id}
            await db.commit()
        return {'id':recovery.id,'status':recovery.status,'previous_inventory':run.id}
    if run.status!='failed':raise HTTPException(409,'Only failed/interrupted runs can be retried; completed outputs are immutable')
    await fresh(db,run)
    if run.attempts>=3:
        reason=payload.reason.strip() if payload else ''
        if token['role'] not in {'admin','reviewer'} or len(reason)<10:raise HTTPException(409,'Three attempts exhausted. A reviewer/operator must document the incident resolution before starting a separate recovery run.')
        recovery=await service.enqueue(db,app,user.id,run.kind,{**run.inputs,'retry_of':run.id,'recovery_reason':reason},run.sources)
        return {'id':recovery.id,'status':recovery.status,'previous_failed_run':run.id}
    await db.execute(update(Run).where(Run.id==id,Run.status=='failed').values(status='queued',error=None,progress=0));await db.commit()
    return {'id':id,'status':'queued'}

class Edit(BaseModel):
    body:str=Field(min_length=1,max_length=100000)
    output_hash:str=Field(min_length=64,max_length=64)

@router.post('/runs/{id}/revision',status_code=201)
async def revision(app_id:int,id:int,payload:Edit,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    app,user=await application(db,token,app_id,True);parent=await run_for(db,app,id)
    if parent.kind!='draft' or parent.status!='completed' or service.digest(parent.output)!=payload.output_hash:raise HTTPException(409,'Reload the completed draft before creating a new revision')
    await fresh(db,parent)
    inputs={**parent.inputs,'revises':parent.id,'human_body':payload.body}
    output={**parent.output,'body':payload.body,'revises':parent.id,'edited_by':user.id}
    output={**output,'validation':service.draft_validation(output)}
    child=await service.enqueue(db,app,user.id,'draft',inputs,parent.sources,output)
    child.model='human revision'
    await db.commit()
    return {'id':child.id,'validation':child.output['validation']}

class RequirementRevision(BaseModel):
    item_id:str=Field(min_length=1,max_length=100)
    required:bool
    source_url:str=Field(min_length=8,max_length=2000)
    notes:str=Field(min_length=10,max_length=4000)
    output_hash:str=Field(min_length=64,max_length=64)

@router.post('/runs/{id}/requirement-revision',status_code=201)
async def requirement_revision(app_id:int,id:int,payload:RequirementRevision,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    app,user=await application(db,token,app_id,True)
    if token['role'] not in {'admin','reviewer'}:raise HTTPException(403,'Reviewer or administrator required')
    parent=await run_for(db,app,id)
    if parent.kind!='inventory' or parent.status!='completed' or service.digest(parent.output)!=payload.output_hash:raise HTTPException(409,'Reload the current inventory')
    await fresh(db,parent)
    if not payload.source_url.startswith('https://'):raise HTTPException(422,'Provide the verified HTTPS instruction source')
    if not any(r['id']==payload.item_id for r in parent.output['items']):raise HTTPException(404,'Requirement not found')
    items=[{**r,'required':payload.required,'applicability_review':{'actor_id':user.id,'notes':payload.notes,'source_url':payload.source_url}} if r['id']==payload.item_id else r for r in parent.output['items']]
    output={**parent.output,'items':items,'revises':parent.id,'inventory_complete':False}
    child=await service.enqueue(db,app,user.id,'inventory',{'revises':parent.id,**payload.model_dump()},parent.sources,output)
    return {'id':child.id,'note':'New inventory revision; earlier extraction and reviewer decisions are retained. Fresh review is required.'}

@router.get('/runs/{id}/reviews')
async def reviews(app_id:int,id:int,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    app,_=await application(db,token,app_id);run=await run_for(db,app,id)
    rows=(await db.execute(select(Review).where(Review.run_id==run.id,Review.organization_id==app.organization_id).order_by(Review.id))).scalars().all()
    return [{'id':r.id,'item_key':r.item_key,'decision':r.decision,'notes':r.notes,'actor_id':r.actor_id,'at':r.created_at,'details':r.details,'source_url':r.source_url,'output_hash':r.output_hash} for r in rows]

class Decision(BaseModel):
    item_key:str=Field(min_length=1,max_length=100)
    decision:Literal['accepted','rejected','needs_information']
    notes:str=Field(min_length=5,max_length=4000)
    source_url:str=Field(default='',max_length=2000)
    output_hash:str=Field(min_length=64,max_length=64)
    evidence_status:Literal['supported','partially_supported','missing','conflicting','awaiting_confirmation']|None=None
    supplied_file_id:int|None=None
    verification:Literal['source_confirmed','portal_confirmed']='source_confirmed'
    inventory_basis:Literal['portal','official_complete_form']='portal'

@router.post('/runs/{id}/review',status_code=201)
async def review(app_id:int,id:int,payload:Decision,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    app,user=await application(db,token,app_id,True)
    if token['role'] not in {'admin','reviewer'}:raise HTTPException(403,'Reviewer or administrator required')
    run=await run_for(db,app,id)
    if run.status!='completed' or service.digest(run.output)!=payload.output_hash:raise HTTPException(409,'Output changed; review the current revision')
    await fresh(db,run)
    allowed={'draft'} if run.kind=='draft' else {r['requirement_id'] for r in run.output.get('matches',[])} if run.kind=='match' else {r['id'] for r in run.output.get('items',[])}|{'inventory_complete'}|{'conflict:'+r['key'] for r in run.output.get('conflicts',[])}
    if payload.item_key not in allowed:raise HTTPException(422,'Unknown review item')
    if payload.decision=='accepted':
        if payload.verification=='portal_confirmed' and not payload.source_url.startswith('https://'):raise HTTPException(422,'Portal confirmation requires its verified HTTPS URL and review notes')
        if run.kind=='draft':
            issues=service.draft_validation(run.output)
            parent=await run_for(db,app,run.inputs['inventory_id'])
            decisions=await service.latest_reviews(db,parent)
            for conflict in parent.output.get('conflicts',[]):
                if decisions.get('conflict:'+conflict['key'],{}).get('decision')!='accepted':issues.append(conflict['detail'])
            if issues:raise HTTPException(422,'Cannot approve: '+' '.join(issues))
        if payload.item_key=='inventory_complete':
            if run.output.get('withheld_batches'):
                raise HTTPException(422,'Withheld source batches remain unresolved. Reanalyze or create a source-reviewed inventory revision before confirming completeness.')
            prior=await service.latest_reviews(db,run)
            active=[r for r in run.output.get('items',[]) if prior.get(r['id'],{}).get('decision')!='rejected']
            if not payload.source_url.startswith('https://') or not active:raise HTTPException(422,'Complete portal inventory requires a verified HTTPS source, active requirements and explicit review notes')
            if any(prior.get(r['id'],{}).get('decision')!='accepted' or r['required'] is None for r in active):raise HTTPException(422,'Review every item and resolve required/conditional applicability before confirming a complete inventory')
            if payload.inventory_basis=='official_complete_form':
                if (app.form_data or {}).get('honda_2027_onboarding'):raise HTTPException(422,'This Honda onboarding still requires confirmation of the complete CyberGrants form and its conditional uploads.')
                if any(r['kind'] in {'question','upload','template'} and r['authority']!='official_guidance' for r in active):raise HTTPException(422,'A non-portal complete form must come from official documents, not supplied outlines or AI suggestions.')
            elif any(r['kind'] in {'question','upload','template'} and prior.get(r['id'],{}).get('details',{}).get('verification')!='portal_confirmed' for r in active):raise HTTPException(422,'Confirm portal questions, uploads and templates against the portal before marking the inventory complete')
        if run.kind=='inventory' and payload.item_key not in {'inventory_complete'} and not payload.item_key.startswith('conflict:'):
            req=next(r for r in run.output['items'] if r['id']==payload.item_key)
            if req['unverified_draft']:
                source=await db.get(IngestionDocument,req['source_id'])
                if not source.reviewed_at:raise HTTPException(422,'Source extraction remains unreviewed. Keep this item provisional until authorized extraction review.')
        if payload.supplied_file_id:
            source=await db.get(IngestionDocument,payload.supplied_file_id)
            doc=await db.get(Document,source.document_id) if source else None
            if not source or not doc or source.organization_id!=app.organization_id or doc.application_id not in (None,app.id) or source.status!='ready' or not source.current or not source.reviewed_at:raise HTTPException(422,'Supply a reviewed current file from this application/organization')
    db.add(Review(organization_id=app.organization_id,run_id=run.id,item_key=payload.item_key,actor_id=token.get('actor_user_id') or user.id,
        decision=payload.decision,notes=payload.notes,source_url=payload.source_url,output_hash=payload.output_hash,
        details={'evidence_status':payload.evidence_status,'supplied_file_id':payload.supplied_file_id,'verification':payload.verification,'inventory_basis':payload.inventory_basis}))
    await db.commit();return {'recorded':True,'note':'Decision applies only to this immutable output version. It does not submit the application.'}

@router.get('/export')
async def export(app_id:int,include_unapproved:bool=False,db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    app,_=await application(db,token,app_id)
    raw,result=await service.package(db,app,include_unapproved=include_unapproved)
    return Response(raw,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="application-{app_id}-{result["package_status"].lower().replace(" ","-")}.zip"'})

@router.get('/runs/{id}/download')
async def download(app_id:int,id:int,format:Literal['txt','docx']='txt',db:AsyncSession=Depends(get_db),token:dict=Depends(get_current_user_token)):
    app,_=await application(db,token,app_id);run=await run_for(db,app,id)
    if run.kind!='draft' or run.status!='completed':raise HTTPException(409,'Completed separate draft required')
    reviews=await service.latest_reviews(db,run)
    label='APPROVED REVIEW DRAFT' if reviews.get('draft',{}).get('decision')=='accepted' else 'UNAPPROVED DRAFT — HUMAN REVIEW REQUIRED'
    validation=service.draft_validation(run.output)
    try:await service.current_sources(db,run)
    except ValueError:validation.append('Sources changed; previous approval does not apply to current evidence.');label='STALE DRAFT — REANALYSIS REQUIRED'
    text=label+'\nApplication '+str(app.id)+', draft revision '+str(run.id)+'\n\n'+run.output['body']+'\n\nValidation: '+('; '.join(validation) or 'Automated checks passed; human and funder review remain required.')
    if format=='docx':
        import io
        from docx import Document as WordDocument
        doc=WordDocument();doc.add_paragraph(text);stream=io.BytesIO();doc.save(stream);raw=stream.getvalue();media='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    else:raw=text.encode();media='text/plain; charset=utf-8'
    return Response(raw,media_type=media,headers={'Content-Disposition':f'attachment; filename="application-{app.id}-draft-{run.id}.{format}"'})
