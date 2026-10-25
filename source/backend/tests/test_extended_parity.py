"""Additional real router workflows with synthetic central identity validation."""
import pytest
from test_integration_audit import client,template_db,headers,ok
from auth import jwt_handler
import test_integration_audit as legacy

@pytest.fixture
def central(client,monkeypatch):
    from db.database import get_db,get_public_db
    import asyncio
    from sqlalchemy import select
    from models.models import User
    async def link_seeded_users():
        async for db in client.app.dependency_overrides[get_db]():
            for user in (await db.execute(select(User))).scalars():
                user.identity_id='synthetic-'+user.role.value
            await db.commit()
    asyncio.run(link_seeded_users())
    client.app.dependency_overrides[get_public_db]=client.app.dependency_overrides[get_db]
    async def validate(token):
        data=jwt_handler.decode_token(token)
        return {'identity_id':'synthetic-'+data['role'],'username':data['username'],'role':data['role'],
                'local_user_id':data['user_id'],'grantflow_access':['read','write']}
    monkeypatch.setattr(jwt_handler,'validate_anthesis_identity',validate)
    return client

def test_foundation_crud(central):legacy.test_foundation_lifecycle(central)
def test_foundation_grant_creation(central):legacy.test_foundation_grant_creation(central)
def test_donor_campaign_crud(central):legacy.test_donor_campaign_and_public_giving(central)
def test_public_campaign_and_donation(central):legacy.test_public_donation_and_private_campaign(central)
def test_negative_donation_validation(central):legacy.test_negative_donation_rejected(central)
def test_provider_configuration(central):legacy.test_provider_credential_lifecycle(central)
def test_search_planning_promotion(central):legacy.test_search_and_planning_promotion(central)
def test_admin_maintenance(central):
    for path in ['/api/admin/fix-encoding','/api/admin/archive-expired-grants']:
        assert central.post(path,headers=headers('grant_writer')).status_code==403
        assert central.post(path,headers=headers()).status_code==200
def test_org_profile_and_reporting(central):
    assert central.patch('/api/organizations/me',headers=headers('grant_writer'),json={'name':'Synthetic updated organization','mission':'Synthetic evidence'}).status_code==200
    assert central.get('/api/analytics/dashboard',headers=headers()).status_code==200
    assert central.get('/api/analytics/grant-pipeline',headers=headers()).status_code==200
def test_donor_and_campaign_update_delete(central):
    donor=ok(central.post('/api/donors',headers=headers(),json={'first_name':'SYNTHETIC','email':'crud@example.test'}),201)
    path='/api/donors/'+str(donor['id'])
    assert central.patch(path,headers=headers(),json={'notes':'Synthetic update'}).status_code==200
    assert central.get(path,headers=headers()).json()['notes']=='Synthetic update'
    assert central.delete(path,headers=headers()).status_code in {200,204}
def test_donation_acknowledgment_is_a_saved_flag(central):
    donation=ok(central.post('/api/donors/donations',headers=headers(),json={'amount':10}),201)
    response=central.patch('/api/donors/donations/'+str(donation['id'])+'/acknowledge',headers=headers())
    assert response.status_code==200 and response.json()['acknowledged'] is True
    campaign=ok(central.post('/api/donors/campaigns',headers=headers(),json={'name':'SYNTHETIC CRUD campaign'}),201)
    path='/api/donors/campaigns/'+str(campaign['id'])
    assert central.patch(path,headers=headers(),json={'description':'Synthetic update'}).status_code==200
    assert central.delete(path,headers=headers()).status_code in {200,204}
