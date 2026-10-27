"""Offline, reversible beta review. Dry run by default; never edits applications.

Stop writers before --apply/--rollback. Journals contain private data: keep outside Git.
Requires a validated storage.py backup containing the exact rows being reviewed.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import zipfile


def load(value):
    return json.loads(value) if value else {}


def fingerprint(row):
    return hashlib.sha256(json.dumps([row['title'],row['funding_agency'],row['source_url']],ensure_ascii=True,separators=(',',':')).encode()).hexdigest()


def review(database, manifest, backup, journal, *, apply=False, sources_only=False):
    # Imports the exact server checks, never a weaker repair-only validator.
    from services.draft_validation import draft_issues, MONEY
    from services.grant_integrity import source_review
    from types import SimpleNamespace
    reviews=json.loads(Path(manifest).read_text())
    if len({r['grant_id'] for r in reviews})!=len(reviews):raise ValueError('Duplicate source review')
    if apply and Path(journal).exists():raise ValueError('Use a new private journal')
    changes=[];now=datetime.now(timezone.utc).isoformat();stats={'packages_reviewed':len(reviews),'verified':0,'withheld':0,'candidates_reviewed':0,'flagged':0,'corrected_revisions':0}
    with tempfile.TemporaryDirectory() as temp,zipfile.ZipFile(backup) as archive:
        metadata=json.loads(archive.read('manifest.json'))
        for name,expected in metadata['sha256'].items():
            if hashlib.sha256(archive.read('data/'+name)).hexdigest()!=expected:raise ValueError('Backup hash mismatch')
        snap=Path(temp)/'before.db';snap.write_bytes(archive.read('data/'+metadata['database']))
        with closing(sqlite3.connect(snap)) as prior,closing(sqlite3.connect(database)) as db:
            db.row_factory=prior.row_factory=sqlite3.Row
            if prior.execute('pragma integrity_check').fetchone()[0]!='ok':raise ValueError('Backup integrity failed')
            db.execute('begin immediate')
            for r in reviews:
                row=db.execute('select * from grants where id=?',(r['grant_id'],)).fetchone()
                before=prior.execute('select * from grants where id=?',(r['grant_id'],)).fetchone()
                if not row or not before or dict(row)!=dict(before):raise ValueError('Grant changed since backup; take a fresh backup and review')
                if fingerprint(row)!=r['fingerprint']:raise ValueError('Source fingerprint changed')
                meta=load(row['meta']);meta['source_review']=r
                checked=source_review(SimpleNamespace(title=row['title'],funding_agency=row['funding_agency'],source_url=row['source_url'],meta=meta))
                if checked['status']!=r['status']:raise ValueError('Incomplete review')
                new=json.dumps(meta)
                changes.append({'table':'grants','id':row['id'],'old':{'meta':row['meta']},'new':{'meta':new}})
                stats['verified' if r['status']=='verified' else 'withheld']+=1
            # Every existing candidate is assessed. Human application columns are never written.
            rows=[] if sources_only else db.execute("select * from organization_records where kind='draft' order by id").fetchall()
            for row in rows:
                before=prior.execute('select * from organization_records where id=?',(row['id'],)).fetchone()
                if not before or dict(row)!=dict(before):raise ValueError('Candidate changed since backup; do not overwrite user work')
                data=load(row['data']);app=db.execute('select * from grant_applications where id=?',(data.get('application_id'),)).fetchone()
                issues=draft_issues(row['body'],{'application':{'amount_requested':app['amount_requested'] if app else None}},'proposal')
                warnings=['Recheck every eligibility/compliance claim against the reviewed original funder notice. Cached packages were previously unverified.']
                if app and app['grant_id'] in (1,17):warnings.append('County Connections source is a historical award announcement; no application requirements are verified.')
                if app and app['grant_id']==36:warnings.append('BEA eligibility requires an FDIC-insured bank/thrift. Nonprofit status alone is insufficient; organizational eligibility evidence is missing.')
                stats['candidates_reviewed']+=1
                quality={'status':'needs_review','issues':issues,'warnings':warnings,'reviewed_at':now,'note':'Original text retained. Corrected candidate requires human evidence review; not accepted.'}
                data['quality_review']=quality;revision=row['revision']+1
                event={'actor':'beta-source-and-quality-review','at':now,'revision':revision,'title':row['title'],'body':row['body'],'data':data,'sha256':hashlib.sha256(row['body'].encode()).hexdigest()}
                history=load(row['history']) if row['history'] else []
                old={k:row[k] for k in ('data','history','revision')};new={'data':json.dumps(data),'history':json.dumps(history+[event]),'revision':revision}
                changes.append({'table':'organization_records','id':row['id'],'old':old,'new':new});stats['flagged']+=1
                # Missing source evidence prevents a factual rewrite. Create a clearly separated
                # information-needed revision, with no invented costs or eligibility claims.
                body='HUMAN REVIEW REQUIRED — CORRECTED REVIEW CANDIDATE\n\nOriginal candidate retained as record '+str(row['id'])+', revision '+str(row['revision'])+'.\n\n'
                body+='[information needed] Confirm the exact funder notice, current round, applicant eligibility, mandatory forms and attachments. Do not reuse the earlier cached requirements.\n\n'
                body+='[information needed] Build an itemized budget using documented quantities and costs, and reconcile it with the saved requested amount before acceptance.\n\n'
                body+='[information needed] Supply named, versioned evidence for outcome claims. Proposed targets must be labelled as targets, not observed results.\n\n'
                body+='Specific findings are retained in the original record quality review and in this candidate metadata. Resolve every finding before human acceptance.'
                if draft_issues(body,{'application':{'amount_requested':app['amount_requested'] if app else None}},'proposal'):raise ValueError('Correction failed server checks')
                corrected={**data,'status':'review','corrected_from':{'record_id':row['id'],'revision':row['revision']},'quality_review':{**quality,'issues':[]}}
                title=('REVIEW CORRECTION: '+row['title'])[:255]
                correction={'organization_id':row['organization_id'],'created_by_id':row['created_by_id'],'kind':'draft','title':title,'body':body,'data':json.dumps(corrected),'revision':1,'history':json.dumps([{'actor':'beta-source-and-quality-review','at':now,'revision':1,'title':title,'body':body,'data':corrected}])}
                changes.append({'table':'organization_records','insert':correction});stats['corrected_revisions']+=1
            if apply:
                # Write and fsync the complete private intent before committing database changes.
                intent={'schema':'gfm.beta-repair.v1','state':'prepared','stats':stats,'changes':changes}
                with Path(journal).open('x',encoding='utf-8') as f:
                    os.chmod(journal,0o600)
                    json.dump(intent,f,indent=2);f.flush();os.fsync(f.fileno())
                for change in changes:
                    if 'insert'in change:
                        values=change['insert'];keys=list(values)
                        cur=db.execute('insert into organization_records ('+','.join(keys)+') values ('+','.join('?'for _ in keys)+')',[values[k]for k in keys]);change['id']=cur.lastrowid
                    else:
                        values=change['new'];db.execute('update '+change['table']+' set '+','.join(k+'=?'for k in values)+' where id=?',[*values.values(),change['id']])
                intent['state']='committing';Path(journal).write_text(json.dumps(intent,indent=2),encoding='utf-8')
                db.commit();intent['state']='committed';Path(journal).write_text(json.dumps(intent,indent=2),encoding='utf-8')
            else:db.rollback()
    return {'mode':'apply' if apply else 'dry_run',**stats}


def rollback(database,journal):
    intent=json.loads(Path(journal).read_text())
    if intent['state']!='committed':raise ValueError('Journal is not committed; inspect interrupted transaction before recovery')
    with closing(sqlite3.connect(database)) as db:
        db.row_factory=sqlite3.Row;db.execute('begin immediate')
        for c in reversed(intent['changes']):
            row=db.execute('select * from '+c['table']+' where id=?',(c['id'],)).fetchone();expected=c.get('new',c.get('insert'))
            if not row or any(row[k]!=v for k,v in expected.items()):raise ValueError('Repaired record changed; rollback refuses to overwrite newer work')
            if 'insert'in c:db.execute('delete from organization_records where id=?',(c['id'],))
            else:db.execute('update '+c['table']+' set '+','.join(k+'=?'for k in c['old'])+' where id=?',[*c['old'].values(),c['id']])
        db.commit()
    intent['state']='rolled_back';Path(journal).write_text(json.dumps(intent,indent=2))
    return {'rolled_back':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('database');parser.add_argument('--manifest');parser.add_argument('--backup');parser.add_argument('--journal',required=True);parser.add_argument('--apply',action='store_true');parser.add_argument('--rollback',action='store_true');parser.add_argument('--writers-stopped',action='store_true');parser.add_argument('--sources-only',action='store_true');args=parser.parse_args()
    if (args.apply or args.rollback)and not args.writers_stopped:parser.error('Stop writers and acknowledge --writers-stopped')
    if args.rollback:print(json.dumps(rollback(args.database,args.journal)))
    else:print(json.dumps(review(args.database,args.manifest,args.backup,args.journal,apply=args.apply,sources_only=args.sources_only)))
