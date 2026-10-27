"""Scoped disposable-workspace cleanup; refuses unrelated users, files or records.

Dry-run default. Only manifests created by beta_test_workspace.py are accepted.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


def cleanup(database,manifest,*,apply=False):
    data=json.loads(Path(manifest).read_text());prefix=data['prefix'];orgs=data['organizations']
    if not prefix.startswith('beta_verify_') or len(orgs)!=2:raise ValueError('Not a disposable beta manifest')
    with closing(sqlite3.connect(database)) as db:
        db.execute('pragma foreign_keys=on');db.execute('begin immediate')
        users=[];files=[];apps=[]
        for org in orgs:
            name=db.execute('select name from organizations where id=?',(org,)).fetchone()
            if not name or not name[0].startswith('SYNTHETIC beta verification '+data['nonce']):raise ValueError('Organization identity mismatch')
            rows=db.execute('select id,username from users where organization_id=?',(org,)).fetchall()
            if not rows or any(not name.startswith(prefix+'_')for _,name in rows):raise ValueError('Unrelated user in disposable organization')
            users+=rows
            apps +=[r[0]for r in db.execute('select id from grant_applications where organization_id=?',(org,))]
            for doc,path in db.execute('select id,file_path from documents where organization_id=?',(org,)):
                target=Path(path).resolve()
                if Path('/var/data/private_documents') not in target.parents:raise ValueError('Document outside disposable storage boundary')
                files.append(target)
        uids=[u[0]for u in users];uq=','.join('?'for _ in uids);oq=','.join('?'for _ in orgs)
        if db.execute(f'select count(*) from grant_applications where applicant_id in ({uq}) and organization_id not in ({oq})',uids+orgs).fetchone()[0]:raise ValueError('Test user owns records outside disposable organizations')
        if apply:
            db.execute(f'delete from document_uses where organization_id in ({oq})',orgs)
            for table in ('ingestion_corrections','document_chunks'):
                db.execute(f'delete from {table} where ingestion_id in (select id from ingestion_documents where organization_id in ({oq}))',orgs)
            db.execute(f'delete from ingestion_documents where organization_id in ({oq})',orgs)
            db.execute(f'delete from browser_sessions where job_id in (select id from automation_jobs where created_by_id in ({uq}))',uids)
            db.execute(f'delete from automation_jobs where created_by_id in ({uq})',uids)
            for table in ('reviews','workflows','grant_analytics'):
                db.execute(f'delete from {table} where application_id in (select id from grant_applications where organization_id in ({oq}))',orgs)
            for table,col in (('grant_planning_profiles','created_by_id'),('notifications','user_id'),('audit_logs','user_id'),('ai_conversations','user_id'),('auth_sessions','user_id'),('auth_invitations','reset_user_id'),('auth_migrated_accounts','user_id')):
                db.execute(f'delete from {table} where {col} in ({uq})',uids)
            db.execute(f'delete from auth_invitations where organization_id in ({oq})',orgs)
            for table in ('organization_records','documents','grant_applications','ingestion_sources'):
                db.execute(f'delete from {table} where organization_id in ({oq})',orgs)
            for _,name in users:db.execute('delete from auth_rate_limits where key=?',(hashlib.sha256(('account:'+name.lower()).encode()).hexdigest(),))
            db.execute(f'delete from users where id in ({uq})',uids)
            db.execute(f'delete from organizations where id in ({oq})',orgs)
            if db.execute('pragma foreign_key_check').fetchall():raise ValueError('Foreign key validation failed; cleanup rolled back')
            db.commit()
            for file in files:file.unlink(missing_ok=True)
        else:db.rollback()
    return {'mode':'apply' if apply else 'dry_run','users':len(users),'applications':len(apps),'files':len(files),'organizations':len(orgs)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('database');p.add_argument('manifest');p.add_argument('--apply',action='store_true');a=p.parse_args()
    print(json.dumps(cleanup(a.database,a.manifest,apply=a.apply)))
