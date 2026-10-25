import asyncio
from datetime import timedelta
from test_ingestion import client, api, upload, drain, headers


def test_correction_requires_review_and_rejects_stale_editor(api):
    row=upload(api,'financial.csv',b'Account,Amount\nRevenue,100.00\n');drain()
    url=f'/api/ingestion/documents/{row["id"]}'
    detail=api.get(url,headers=headers()).json()
    body={'text':'Account | Amount\nRevenue | 120.50','reason':'Verified against synthetic original',
          'revision':detail.get('extraction_revision','missing')}
    assert api.post(url+'/corrections',json=body,headers=headers()).status_code==403
    response=api.post(url+'/corrections',json=body,headers=headers('admin'))
    assert response.status_code==200,response.text
    updated=api.get(url,headers=headers()).json()
    assert updated['status']=='needs_review' and updated['extracted']['parts'][0]['text']==body['text']
    assert api.get('/api/ingestion/search?q=120.50',headers=headers()).json()==[]
    assert api.post(url+'/corrections',json=body,headers=headers('admin')).status_code==409
    assert api.post(url+'/review',json={'confirmed':True,'sha256':row['sha256'],'revision':body['revision']},headers=headers('admin')).status_code==409
    assert api.post(url+'/review',json={'confirmed':True,'sha256':row['sha256'],'revision':updated['extraction_revision']},headers=headers('admin')).status_code==200
    assert api.get('/api/ingestion/search?q=120.50',headers=headers()).json()
    audit=api.get(url+'/corrections',headers=headers()).json()
    assert '120.50' in audit[0]['diff'] and audit[0]['reason']==body['reason']
    assert api.delete(url,headers=headers('admin')).status_code==200
    audit=api.get(url+'/corrections',headers=headers()).json()
    assert '120.50' not in str(audit) and body['reason'] not in str(audit)


def test_freshness_and_monitor_are_scoped(api):
    from db import database
    from models.models import IngestionDocument
    from services.document_ingestion import now, receive
    row=upload(api);drain()
    async def age():
        async with database.AsyncSessionLocal() as db:
            item=await db.get(IngestionDocument,row['id'])
            item.created_at=now()-timedelta(days=100)
            item.checked_at=now()  # polling unchanged bytes must not make old evidence fresh
            await db.commit()
            await receive(db,2,2,b'Other tenant private','secret.txt')
    asyncio.run(age())
    response=api.get('/api/ingestion/monitor',headers=headers())
    assert response.status_code==200,response.text
    report=response.json()
    assert report['counts']['ready']==1 and report['counts'].get('queued',0)==0
    assert report['stale_documents']==1
    assert api.get('/api/ingestion/documents',headers=headers()).json()[0]['stale']
    async def evidence():
        from services.document_ingestion import retrieval
        async with database.AsyncSessionLocal() as db:return await retrieval(db,1,'education')
    assert 'Evidence review overdue' in asyncio.run(evidence())[0]['excerpt']


def test_evidence_dates_survive_poll_history_and_reprocessing(api):
    from services.document_ingestion import now
    row=upload(api);drain();url=f'/api/ingestion/documents/{row["id"]}'
    today=now().date()
    body={'as_of':str(today-timedelta(days=60)),'review_due':str(today+timedelta(days=10))}
    assert api.put(url+'/freshness',json=body,headers=headers()).status_code==403
    assert api.put(url+'/freshness',json=body,headers=headers('admin')).status_code==200
    assert api.post(url+'/retry',headers=headers()).status_code==200
    drain()
    item=api.get(url,headers=headers()).json()
    assert item['freshness']['date_confirmed'] and not item['stale']
    assert item['freshness']['as_of']==body['as_of']
    body['as_of']=str(today+timedelta(days=1))
    assert api.put(url+'/freshness',json=body,headers=headers('admin')).status_code==422
