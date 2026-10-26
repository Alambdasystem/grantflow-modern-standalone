"""Install a verified private migration archive while the app is in maintenance.

SSH/SCP authenticates the operator; this is intentionally not an HTTP endpoint.
Existing destination records are never overwritten or linked by email/name.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import urllib.request
from contextlib import closing
from storage import backup,restore


def install(root,archive,expected,port):
    root=Path(root).resolve();archive=Path(archive).resolve()
    if root!=Path('/var/data') or not os.path.ismount(root):
        raise ValueError('Expected the approved mounted persistent disk')
    if not (root/'.maintenance').is_file(): raise ValueError('Enter maintenance before installation')
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=5) as response:
        if not json.load(response).get('maintenance'): raise ValueError('Application writers are not quiesced')
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest!=expected: raise ValueError('Private archive checksum mismatch')
    database=root/'grantflow.db'
    with closing(sqlite3.connect(database)) as db:
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        runtime={'auth_control','auth_sessions','auth_rate_limits','auth_invitations','schema_versions'}
        populated={t:db.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in tables if t not in runtime}
        if any(populated.values()):
            raise ValueError('Destination has existing records: preserve backup and obtain an explicit collision/remapping plan')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    rollback=root/'private-migration'/'destination-before-import.zip'
    if rollback.exists(): raise ValueError('A previous migration backup exists; review before another install')
    # backup() writes outside the data root; retain the completed protected
    # archive on the disk only after it is closed.
    with tempfile.TemporaryDirectory() as temp:
        temp=Path(temp);snap=temp/'destination.zip'
        backup(root,snap)
        candidate=temp/'candidate';restore(archive,candidate)
        if not (candidate/'grantflow.db').is_file(): raise ValueError('Candidate database missing')
        with closing(sqlite3.connect(candidate/'grantflow.db')) as db:
            if db.execute('SELECT bootstrapped FROM auth_control WHERE id=1').fetchone()!=(1,):
                raise ValueError('Imported administrator bootstrap must be closed')
            if db.execute('SELECT external_jobs_paused FROM migration_safety WHERE id=1').fetchone()!=(1,):
                raise ValueError('Imported external jobs must be held')
            if not db.execute('SELECT count(*) FROM auth_migrated_accounts').fetchone()[0]:
                raise ValueError('Explicit imported identity mapping missing')
        files=[p for p in candidate.rglob('*') if p.is_file() and p.name!='.maintenance']
        for item in files:
            rel=item.relative_to(candidate);target=root/rel
            if rel!=Path('grantflow.db') and target.exists():
                raise ValueError('Destination file collision; review explicitly')
        if shutil.disk_usage(root).free < sum(x.stat().st_size for x in files)+snap.stat().st_size+64*1024*1024:
            raise ValueError('Insufficient persistent disk headroom')
        rollback.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(snap,rollback);os.chmod(rollback,0o600)
        installed=[];old=root/'private-migration'/'destination-before-import.db'
        try:
            for item in files:
                if item.name=='grantflow.db' and item.parent==candidate: continue
                target=root/item.relative_to(candidate);target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(item,target);os.chmod(target,0o600);installed.append(target)
            database.replace(old)
            shutil.copy2(candidate/'grantflow.db',database);os.chmod(database,0o600)
            for suffix in ('-wal','-shm'):
                sidecar=Path(str(database)+suffix)
                if sidecar.exists():sidecar.unlink()
            if os.geteuid()==0:
                for target in [database,rollback,old,*installed]:os.chown(target,10001,10001)
                for directory in [p for p in root.rglob('*') if p.is_dir()]:os.chown(directory,10001,10001)
        except Exception:
            if old.exists():old.replace(database)
            for target in installed:target.unlink(missing_ok=True)
            raise
    return {'installed':True,'backup':'private-migration/destination-before-import.zip',
            'maintenance_remains_active':True,'external_jobs_paused':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive');parser.add_argument('--sha256',required=True)
    parser.add_argument('--root',default='/var/data');parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','10000')))
    args=parser.parse_args()
    print(json.dumps(install(args.root,args.archive,args.sha256,args.port)))
