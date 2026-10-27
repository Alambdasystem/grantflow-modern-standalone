"""Operator-only disposable beta identities. No existing user is modified.

The private manifest is the cleanup authority. Never publish it or print passwords.
Use the normal login/invitation/account APIs after provisioning.
"""
import json
import os
from pathlib import Path
import secrets
import sqlite3
import uuid
from contextlib import closing


def create(database,manifest):
    from auth.standalone import password_hash
    manifest=Path(manifest)
    if manifest.exists():raise ValueError('Use a new private manifest')
    nonce=secrets.token_hex(8);prefix='beta_verify_'+nonce
    result={'base':'https://grantflow-modern-staging.onrender.com','nonce':nonce,'prefix':prefix,'accounts':{},'organizations':[]}
    with closing(sqlite3.connect(database)) as db,db:
        for index in range(2):
            org=db.execute('insert into organizations(name,mission,description) values(?,?,?)',('SYNTHETIC beta verification '+nonce+' '+str(index),'Synthetic youth education evidence','Disposable verification workspace')).lastrowid
            result['organizations'].append(org)
            for role in (['admin','grant_writer','reviewer','viewer'] if index==0 else ['grant_writer']):
                key=role if index==0 else 'other_writer';name=prefix+'_'+key;password=secrets.token_urlsafe(32)
                uid=db.execute('insert into users(username,email,identity_id,hashed_password,role,organization_id,is_active,is_approved) values(?,?,?,?,?,?,1,1)',(name,name+'@example.com','standalone:'+uuid.uuid4().hex,password_hash(password),role,org)).lastrowid
                result['accounts'][key]={'id':uid,'username':name,'password':password,'organization_id':org}
        with manifest.open('x')as file:json.dump(result,file)
        os.chmod(manifest,0o600)
    return {'temporary_accounts':len(result['accounts']),'temporary_organizations':len(result['organizations'])}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('database');p.add_argument('manifest');a=p.parse_args()
    print(json.dumps(create(a.database,a.manifest)))
