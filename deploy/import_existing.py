"""Offline, operator-only conversion of an exact Modern snapshot.

Run against an isolated copy with network disabled. No username/email linking,
no generated credentials, and no edits to the original installation. The source
backup, central snapshot and conversion plan remain private runtime material.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path, PureWindowsPath
import sqlite3
import ntpath


def rows_digest(db,table):
    rows=db.execute('SELECT * FROM "'+table+'" ORDER BY rowid').fetchall()
    return hashlib.sha256(json.dumps([list(r) for r in rows],default=str,separators=(',',':')).encode()).hexdigest()


def canonical_asset(reference,files):
    """Normalize Windows separator/case variants using explicit copied assets.

    A relative reference must match a full directory suffix, never a filename
    alone. Ambiguous or missing screenshot references require operator review.
    """
    if reference.startswith('/var/data/'):
        rel=reference.removeprefix('/var/data/')
        if rel not in files: raise ValueError('Destination asset absent from verified file manifest')
        return reference
    original=PureWindowsPath(reference)
    if not original.is_absolute() and '..' in original.parts: raise ValueError('Unreviewed relative traversal')
    value=PureWindowsPath(ntpath.normpath(reference))
    if len(value.parts)<2: raise ValueError('Unreviewed asset reference')
    normalized=str(value).casefold()
    matches=[]
    for rel,item in files.items():
        source=str(PureWindowsPath(ntpath.normpath(item['source']))).casefold()
        if source==normalized or (not value.is_absolute() and source.endswith('\\'+normalized)):
            matches.append('/var/data/'+rel)
    if len(matches)!=1: raise ValueError('Missing or ambiguous original asset reference')
    return matches[0]


def normalize_screenshots(db,files,change):
    for id,raw in db.execute('SELECT id,screenshots FROM automation_jobs').fetchall():
        before=json.loads(raw or '[]')
        after=[canonical_asset(value,files) for value in before]
        if after!=before:
            change('automation_jobs',id,'screenshots',raw,json.dumps(after),'Canonicalize verified Windows screenshot references')


def convert(database,central_file,plan_file,source_tag,cutoff):
    from auth.legacy_passwords import supported
    central=json.loads(Path(central_file).read_text(encoding='utf-8-sig'))
    if isinstance(central,list): central={u['username']:u for u in central}
    stable={}
    for name,record in central.items():
        key=str(record.get('identity_id') or record.get('user_id') or name)
        if key in stable: raise ValueError('Ambiguous stable central identity')
        stable[key]=(name,record)
    plan=json.loads(Path(plan_file).read_text())
    changes=[]; accounts=[]; counts={}; namespace=hashlib.sha256(source_tag.encode()).hexdigest()[:16]
    with sqlite3.connect(database) as db:
        db.row_factory=sqlite3.Row
        if db.execute('SELECT count(*) FROM auth_migrated_accounts').fetchone()[0]:
            raise ValueError('Snapshot was already converted; use a new isolated copy')
        users=[dict(r) for r in db.execute('SELECT * FROM users ORDER BY id')]
        reserved={r['username'].lower() for r in users}
        def change(table,id,column,before,after,reason):
            if before==after: return
            changes.append({'table':table,'id':id,'column':column,'before':before,'after':after,'reason':reason})
            db.execute(f'UPDATE "{table}" SET "{column}"=? WHERE id=?',(after,id))
        for user in users:
            original=user.get('identity_id')
            match=stable.get(original) if original else None
            permitted=bool(user['is_active'] and user['is_approved'])
            role=user['role'];scopes=['read'] if role=='viewer' else ['read','write']
            alias=None; credential=user['hashed_password'];credential_source='modern-local'
            if match:
                central_name,record=match
                credential=record.get('password') or '';credential_source='central-stable-id'
                grants=record.get('app_access');grants=grants if isinstance(grants,dict) else {}
                access=grants.get('grantflow',[]);access=[access] if isinstance(access,str) else access
                access=access if isinstance(access,list) else []
                roles=record.get('app_roles');roles=roles if isinstance(roles,dict) else {}
                central_role=roles.get('grantflow','viewer')
                if central_role not in {'admin','grant_writer','reviewer','viewer'}: central_role='viewer'
                role='viewer' if 'viewer' in {role,central_role} else role if central_role=='admin' else central_role
                scopes=[s for s in scopes if s in access or 'all' in access]
                permitted=permitted and bool({'read','all'}&set(access)) and 'grantflow' not in (record.get('app_access_denied') or [])
                permitted=permitted and record.get('approved',True) and bool(record.get('is_active',record.get('active',True))) and record.get('disabled') is not True
                candidate=central_name.lower()
                if candidate!=user['username'].lower() and candidate not in reserved:
                    alias=candidate;reserved.add(candidate)
            if not original:
                new_identity=f'migrated:{namespace}:{user["id"]}'
                change('users',user['id'],'identity_id',None,new_identity,'Explicit source table primary-key namespace')
            usable=credential.startswith('scrypt32768$') or supported(credential)
            # Never put password hashes in the public conversion log.
            if credential!=user['hashed_password']:
                db.execute('UPDATE users SET hashed_password=? WHERE id=?',(credential if usable else '!recovery-required!',user['id']))
            db.execute('INSERT INTO auth_migrated_accounts(user_id,source_identity,credential_source,login_alias,permitted,role_ceiling,scopes) VALUES(?,?,?,?,?,?,?)',
                (user['id'],original or source_tag+'/users/'+str(user['id']),credential_source,alias,permitted,role,json.dumps(scopes)))
            accounts.append({'user_id':user['id'],'username':user['username'],'source_identity':original,
                'credential_source':credential_source,'password_supported':usable,'permitted':bool(permitted),
                'effective_role':role,'login_alias':alias,'recovery_required':not usable})
        for item in plan.get('cell_changes',[]):
            allowed={'documents':{'file_path'},'automation_jobs':{'screenshots','steps_log','result'},'browser_sessions':{'session_state'}}
            if item['column'] not in allowed.get(item['table'],set()): raise ValueError('Unreviewed file-reference change')
            before=db.execute(f'SELECT "{item["column"]}" FROM "{item["table"]}" WHERE id=?',(item['id'],)).fetchone()
            if not before or before[0]!=item['before']: raise ValueError('Source changed after file-reference planning')
            change(item['table'],item['id'],item['column'],item['before'],item['after'],'Relocate source file reference beneath persistent disk')
        normalize_screenshots(db,plan.get('files',{}),change)
        # Preserve orphan records; detach only missing nullable references and
        # retain the exact old FK in a reversible, private conversion journal.
        for table,rowid,parent,fkid in db.execute('PRAGMA foreign_key_check').fetchall():
            fk=next(r for r in db.execute(f'PRAGMA foreign_key_list("{table}")') if r[0]==fkid)
            column=fk[3]
            nullable=next(r[3]==0 for r in db.execute(f'PRAGMA table_info("{table}")') if r[1]==column)
            if table!='donations' or column not in {'donor_id','campaign_id'} or not nullable:
                raise ValueError('Unreviewed source foreign-key defect')
            before=db.execute(f'SELECT "{column}" FROM "{table}" WHERE rowid=?',(rowid,)).fetchone()[0]
            change(table,rowid,column,before,None,'Pre-existing missing parent; record retained, missing reference detached')
        for job in db.execute("SELECT id,status FROM automation_jobs WHERE status IN ('queued','running','awaiting_approval')").fetchall():
            change('automation_jobs',job['id'],'status',job['status'],'paused','Imported pending job requires review; never replay')
        for session in db.execute('SELECT id,is_active FROM browser_sessions WHERE is_active=1').fetchall():
            change('browser_sessions',session['id'],'is_active',1,0,'Imported browser sessions cannot resume')
        db.execute('INSERT OR REPLACE INTO migration_safety(id,external_jobs_paused,source_cutoff) VALUES(1,1,?)',(cutoff,))
        if not any(a['permitted'] and a['password_supported'] and a['effective_role']=='admin' for a in accounts):
            raise ValueError('No existing supported administrator; resolve controlled recovery before import')
        db.execute('INSERT OR REPLACE INTO auth_control(id,bootstrapped) VALUES(1,1)')
        db.execute('DELETE FROM auth_sessions');db.execute('DELETE FROM auth_invitations');db.execute('DELETE FROM auth_rate_limits')
        db.execute('CREATE TABLE migration_conversion_journal(id INTEGER PRIMARY KEY,source_cutoff TEXT NOT NULL,change_json TEXT NOT NULL)')
        for item in changes:
            db.execute('INSERT INTO migration_conversion_journal(source_cutoff,change_json) VALUES(?,?)',(cutoff,json.dumps(item)))
        if db.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('Unresolved relationship defects')
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Database integrity failure')
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        counts={t:db.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in tables}
        db.commit()
    return {'source_cutoff':cutoff,'counts':counts,'accounts':accounts,'changes':changes}


async def initialize():
    from db.database import init_db,engine
    await init_db();await engine.dispose()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',required=True);p.add_argument('--central',required=True)
    p.add_argument('--plan',required=True);p.add_argument('--source-tag',required=True)
    p.add_argument('--cutoff',required=True);p.add_argument('--private-report',required=True)
    args=p.parse_args()
    if '/anthesis/' in Path(args.database).resolve().as_posix().lower():
        raise ValueError('Never convert a database beneath the original Anthesis installation')
    from config import settings
    from urllib.parse import urlsplit
    if Path(urlsplit(settings.DATABASE_URL).path).resolve()!=Path(args.database).resolve():
        raise ValueError('Initialization database must match explicit offline target')
    asyncio.run(initialize())
    report=convert(args.database,args.central,args.plan,args.source_tag,args.cutoff)
    Path(args.private_report).write_text(json.dumps(report,indent=2))
    print(json.dumps({'converted_users':len(report['accounts']),'recovery_required':sum(a['recovery_required'] for a in report['accounts']),
                      'blocked_by_source_access':sum(not a['permitted'] for a in report['accounts']),
                      'changes':len(report['changes']),'foreign_keys':'PASS','integrity':'PASS'}))
