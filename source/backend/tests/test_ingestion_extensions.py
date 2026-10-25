import sys
from pathlib import Path
import pytest
import asyncio
import json
import httpx
from test_ingestion import client, api, headers, drain
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def test_cloud_rejects_credential_redirect():
    from services.cloud_documents import checked_url, CloudSourceError
    with pytest.raises(CloudSourceError): checked_url('http://localhost/secrets','graph')
    with pytest.raises(CloudSourceError): checked_url('https://graph.microsoft.com.evil.test/v1.0','graph')
    assert checked_url('https://graph.microsoft.com/v1.0/drives/test','graph')


def test_ocr_rows_preserve_positions_and_uncertainty():
    from services.document_extract import ocr_table
    result=[[[[10,10],[90,10],[90,30],[10,30]],'Revenue',.99],
            [[[200,10],[280,10],[280,30],[200,30]],'18432.75',.72],
            [[[10,50],[90,50],[90,70],[10,70]],'Expenses',.98],
            [[[200,50],[280,50],[280,70],[200,70]],'6001.25',.99]]
    table=ocr_table(result,'page 1')
    assert table['rows']==[['Revenue','18432.75'],['Expenses','6001.25']]
    assert table['requires_review'] and table['cells'][0][1]['confidence']==.72


@pytest.mark.parametrize('provider', ['google_drive', 'sharepoint'])
def test_cloud_download_and_no_bearer_on_redirect(tmp_path, provider):
    from services.cloud_documents import documents
    credentials=tmp_path/'credentials.json'
    credentials.write_text(json.dumps({'tenant_id':'test','app_id':'test','client_secret':{'password':'fake'},
        'client_id':'fake','refresh_token':'fake'}))
    calls=[]
    def handle(req):
        calls.append(req)
        if req.method=='POST': return httpx.Response(200,json={'access_token':'synthetic-only'})
        if req.url.path.endswith('/children'):
            return httpx.Response(200,json={'value':[{'id':'abc','name':'mission.txt','file':{}}]})
        if req.url.path.endswith('/content'):
            return httpx.Response(302,headers={'location':'https://tenant.sharepoint.com/download'})
        if req.url.path=='/drive/v3/files':
            return httpx.Response(200,json={'files':[{'id':'abc','name':'mission.txt','mimeType':'text/plain'}]})
        return httpx.Response(200,content=b'Mission: synthetic education')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return [row async for row in documents({'provider':provider,'credential_file':str(credentials),
                'folder_id':'folder','drive_id':'drive'},client)]
    assert asyncio.run(run())==[('abc','mission.txt',b'Mission: synthetic education')]
    if provider=='sharepoint': assert 'authorization' not in calls[-1].headers


def test_cloud_denial_and_untrusted_pagination():
    from services.cloud_documents import request, CloudSourceError
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(403))) as client:
            with pytest.raises(CloudSourceError,match='access denied'):
                await request(client,'https://graph.microsoft.com/v1.0/drives/test','graph','secret')
            with pytest.raises(CloudSourceError,match='untrusted'):
                await request(client,'https://evil.test/next','graph','secret')
    asyncio.run(run())


def test_cloud_outage_is_bounded(monkeypatch):
    from services import cloud_documents as cloud
    from unittest.mock import AsyncMock
    monkeypatch.setattr(cloud.asyncio,'sleep',AsyncMock())
    calls=[]
    def handle(req):
        calls.append(req)
        return httpx.Response(503)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(cloud.CloudSourceError):
                await cloud.request(client,'https://graph.microsoft.com/v1.0/drives/test','graph','fake')
    asyncio.run(run())
    assert len(calls)==3


def test_cloud_scheduler_versions_rename_and_failure_retention(api,tmp_path,monkeypatch):
    from config import settings
    from services import cloud_documents, document_ingestion as service
    from db import database
    from models.models import IngestionSource
    manifest=tmp_path/'sources.json'
    manifest.write_text(json.dumps([{'key':'cloud-test','label':'Synthetic cloud contract test',
        'provider':'google_drive','organization_id':1,'created_by_id':1,'enabled':True}]))
    monkeypatch.setattr(settings,'INGESTION_SOURCE_MANIFEST',str(manifest))
    state={'name':'mission.txt','raw':b'Mission: science education','failed':False}
    async def cloud(cfg):
        if state['failed']: raise cloud_documents.CloudSourceError('Cloud provider unavailable')
        yield 'stable-provider-id',state['name'],state['raw']
    monkeypatch.setattr(cloud_documents,'documents',cloud)
    async def poll():
        async with database.AsyncSessionLocal() as db:
            source=await db.get(IngestionSource,1)
            if source:source.next_poll=None;await db.commit()
        await service.schedule()
    asyncio.run(poll());drain()
    state['name']='renamed.txt'
    asyncio.run(poll())
    assert len(api.get('/api/ingestion/documents',headers=headers()).json())==1
    state['raw']=b'Mission: updated education research'
    asyncio.run(poll());drain()
    rows=api.get('/api/ingestion/documents',headers=headers()).json()
    assert len(rows)==2 and rows[0]['version']==2 and rows[0]['name']=='renamed.txt'
    state['failed']=True;asyncio.run(poll())
    assert api.get('/api/ingestion/search?q=research',headers=headers()).json()
    assert api.get('/api/ingestion/sources',headers=headers()).json()['sources'][0]['error']=='Cloud provider unavailable'
