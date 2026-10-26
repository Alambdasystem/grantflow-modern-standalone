"""Offline SQLite + file snapshot. Caller MUST stop gateway/backend/other writers.

Restore refuses existing data and validates all content before creating the target.
Archives contain private data: protect/encrypt them outside Git.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def backup(data, archive, database='grantflow.db'):
    data, archive = Path(data), Path(archive)
    if archive.exists() or not (data / database).is_file():
        raise ValueError('Require a new archive and an existing database')
    if data.resolve() in archive.resolve().parents:
        raise ValueError('Archive must be outside the data directory')
    if any(p.is_symlink() for p in data.rglob('*')):
        raise ValueError('Symlinks are not supported')
    with tempfile.TemporaryDirectory() as temp:
        snap = Path(temp) / 'snapshot.db'
        with closing(sqlite3.connect(f'file:{(data / database).resolve().as_posix()}?mode=ro', uri=True)) as src, closing(sqlite3.connect(snap)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Database integrity check failed')
        files = {p.relative_to(data).as_posix(): p for p in data.rglob('*') if p.is_file()
                 and p.name not in {database, database + '-wal', database + '-shm'}}
        files[database] = snap
        manifest = {name: digest(p) for name, p in files.items()}
        archive.parent.mkdir(parents=True, exist_ok=True)
        # x prevents accidental replacement of a previous backup.
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
            for name, p in files.items():
                z.write(p, 'data/' + name)
            z.writestr('manifest.json', json.dumps({'database': database, 'sha256': manifest}, sort_keys=True))
    return {'files': len(files), 'archive_sha256': digest(archive)}


def restore(archive, target):
    target = Path(target)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError('Restore target must be empty')
    with zipfile.ZipFile(archive) as z, tempfile.TemporaryDirectory() as temp:
        manifest = json.loads(z.read('manifest.json'))
        hashes = manifest['sha256']
        names = z.namelist()
        if len(names) != len(set(names)) or set(names) != {'manifest.json', *('data/' + n for n in hashes)}:
            raise ValueError('Unexpected or duplicate archive entries')
        for name, expected in hashes.items():
            path = PurePosixPath(name)
            if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe archive path')
            dest = Path(temp) / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open('data/' + name) as src, dest.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            if digest(dest) != expected:
                raise ValueError('Archive content checksum mismatch')
        db = Path(temp) / manifest['database']
        if manifest['database'] not in hashes:
            raise ValueError('Missing database')
        with closing(sqlite3.connect(db)) as conn:
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Database integrity/foreign key failure')
        target.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or any(p.is_symlink() for p in target.parents):
            raise ValueError('Symlink target is not supported')
        shutil.copytree(temp, target, dirs_exist_ok=True)
    return {'restored_files': len(hashes)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup', 'restore'])
    parser.add_argument('source')
    parser.add_argument('target')
    parser.add_argument('--writers-stopped', action='store_true', required=True)
    args = parser.parse_args()
    print(json.dumps(globals()[args.operation](args.source, args.target)))
