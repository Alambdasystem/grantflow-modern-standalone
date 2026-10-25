"""Dry-run-first, explicit identity link rehearsal. Never infer a link from email.

This lab-only tool refuses paths outside /tmp or /data. It changes neither central
credentials nor central roles. A separate access decision is still required.
"""
import argparse
import json
from pathlib import Path
import sqlite3

def reconcile(database, decision, apply=False):
    path=Path(database).resolve()
    if not any(path.is_relative_to(Path(p)) for p in ['/tmp','/data']):
        raise ValueError('Lab-only repair refuses original/host database paths')
    if not decision.get('approved_by') or not decision.get('evidence_reference'):
        raise ValueError('Explicit reviewed identity evidence and approver required')
    required={'legacy_user_id','expected_username','expected_org_id','expected_application_count','central_identity_id'}
    if not required.issubset(decision):
        raise ValueError('Incomplete explicit mapping')
    with sqlite3.connect(path) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE' if apply else 'BEGIN')
        source=db.execute('SELECT * FROM users WHERE id=?',(decision['legacy_user_id'],)).fetchone()
        if source is None or source['username']!=decision['expected_username'] or source['organization_id']!=decision['expected_org_id']:
            raise ValueError('Legacy user/organization precondition failed')
        count=db.execute('SELECT COUNT(*) FROM grant_applications WHERE applicant_id=?',(source['id'],)).fetchone()[0]
        if count!=decision['expected_application_count']:
            raise ValueError('Application-count precondition failed')
        identity=decision['central_identity_id']
        if source['identity_id']==identity:
            db.rollback()
            return {'status':'already_linked','application_count':count}
        if source['identity_id']:
            raise ValueError('Legacy user already linked to a different identity')
        target=db.execute('SELECT * FROM users WHERE identity_id=?',(identity,)).fetchone()
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='identity_migration_map'").fetchone():
            mapped=db.execute('SELECT identity_id FROM identity_migration_map WHERE source=? AND source_user_id=?',('gfm',str(source['id']))).fetchone()
            if mapped and mapped[0]!=identity:
                raise ValueError('Durable migration map disagrees; manual conflict review required')
        if target:
            if target['organization_id'] is not None:
                raise ValueError('Existing projection has an organization; manual conflict review required')
            for table, in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                if not table.replace('_','').isalnum():
                    raise ValueError('Unexpected table name')
                for fk in db.execute('PRAGMA foreign_key_list("'+table+'")').fetchall():
                    if fk[2]=='users':
                        column=fk[3]
                        if db.execute('SELECT COUNT(*) FROM "'+table+'" WHERE "'+column+'"=?',(target['id'],)).fetchone()[0]:
                            raise ValueError('Existing projection owns records; automatic consolidation refused')
        result={'status':'dry_run','legacy_user_id':source['id'],'empty_projection_id':target['id'] if target else None,
                'organization_id':source['organization_id'],'application_count':count,'roles_changed':False}
        if not apply:
            db.rollback()
            return result
        if target:
            db.execute('DELETE FROM users WHERE id=?',(target['id'],))
        db.execute('UPDATE users SET identity_id=? WHERE id=? AND identity_id IS NULL',(identity,source['id']))
        db.execute('CREATE TABLE IF NOT EXISTS identity_migration_map (source TEXT NOT NULL, source_user_id TEXT NOT NULL, identity_id TEXT NOT NULL, PRIMARY KEY(source,source_user_id))')
        db.execute('INSERT INTO identity_migration_map(source,source_user_id,identity_id) VALUES (?,?,?) ON CONFLICT(source,source_user_id) DO UPDATE SET identity_id=excluded.identity_id',('gfm',str(source['id']),identity))
        db.execute('CREATE TABLE IF NOT EXISTS lab_identity_link_audit (id INTEGER PRIMARY KEY, decision TEXT NOT NULL)')
        db.execute('INSERT INTO lab_identity_link_audit(decision) VALUES (?)',(json.dumps({**result,**decision}),))
        db.commit()
        return {**result,'status':'applied'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--decision',required=True);p.add_argument('--apply',action='store_true')
    args=p.parse_args()
    print(json.dumps(reconcile(args.database,json.loads(Path(args.decision).read_text()),args.apply)))
