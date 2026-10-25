"""Explicit migration of legacy app identities into Anthesis users.json.

Dry-run is the default. Reports omit usernames, email addresses, passwords, and
password hashes; conflict references are deterministic, non-reversible digests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
import uuid
import copy
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(os.getenv("GFM_LEGACY_IMPORT_ROOT", Path(__file__).resolve().parents[2] / ".private" / "legacy")).resolve()
USERS_PATH = ROOT / "users.json"
SOURCES = [
    ("gfm", ROOT / "grantflow-modern" / "backend" / "grantflow_modern.db", "users", "hashed_password"),
    ("legacy_grantflow", ROOT / "grant_flow.db", "grant_users", "password_hash"),
    ("legacy_devops_grantflow", ROOT / "anthesis_devops.db", "grant_users", "password_hash"),
]
SENTINEL_HASH = "!anthesis-central-auth-disabled!"


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _hash_kind(value: Any) -> str:
    encoded = str(value or "")
    if encoded.startswith("pbkdf2:"):
        return "werkzeug-pbkdf2"
    if encoded.startswith("scrypt:"):
        return "werkzeug-scrypt"
    if encoded.startswith(("$2a$", "$2b$", "$2y$")):
        return "bcrypt"
    if len(encoded) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in encoded):
        return "sha256-hex"
    return "unsupported-or-missing"


def _ref(source: str, source_id: Any, username: Any, email: Any) -> str:
    raw = "\0".join((source, str(source_id), _norm(username), _norm(email)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _read_users() -> tuple[Any, list[dict[str, Any]]]:
    raw = json.loads(USERS_PATH.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        records = []
        for username, value in raw.items():
            if isinstance(value, dict):
                record = dict(value)
                record.setdefault("username", username)
                records.append(record)
    elif isinstance(raw, list):
        records = [dict(value) for value in raw if isinstance(value, dict)]
    else:
        raise ValueError("users.json must be an object or list")
    return raw, records


def _write_users(records: list[dict[str, Any]]) -> None:
    payload = {str(record["username"]): record for record in records if record.get("username")}
    temporary = USERS_PATH.with_suffix(".json.identity-tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, USERS_PATH)


def _read_source(source: str, db_path: Path, table: str, hash_column: str) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
        if not columns:
            return []
        rows = [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
        has_map = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='identity_migration_map'").fetchone()
        if has_map:
            mapped = dict(connection.execute('SELECT source_user_id, identity_id FROM identity_migration_map WHERE source=?', (source,)))
            for row in rows:
                if str(row.get('id')) in mapped:
                    row['identity_id'] = mapped[str(row['id'])]
        return rows
    finally:
        connection.close()


def _make_backup() -> Path:
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "Anthesis" / "identity-cutover-backups"
    backup = base / (time.strftime("%Y%m%d-%H%M%S") + '-' + uuid.uuid4().hex[:8])
    backup.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {"created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "files": []}
    for source, path, _, _ in [("users", USERS_PATH, "", ""), *SOURCES]:
        if not path.exists():
            manifest["files"].append({"source": str(path), "status": "missing"})
            continue
        target = backup / path.name
        if path.suffix == ".db":
            source_db = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
            target_db = sqlite3.connect(target)
            source_db.backup(target_db)
            target_db.close()
            source_db.close()
        else:
            shutil.copy2(path, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest["files"].append({"source": str(path), "backup": str(target), "sha256": digest})
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return backup


def _source_active(source: str, record: dict[str, Any]) -> bool:
    active = bool(record.get("is_active", record.get("active", True)))
    if source == "gfm":
        active = active and bool(record.get("is_approved", True))
    return active and not bool(record.get("disabled", False))


def _source_role(source: str, record: dict[str, Any]) -> tuple[str, bool]:
    old_role = str(record.get("role") or "").strip().casefold()
    privileged_conflict = old_role == "admin"
    if old_role == "reviewer" and source == "gfm":
        role = "reviewer"
    elif old_role == "viewer" and source == "gfm":
        role = "viewer"
    else:
        role = "grant_writer"
    return role, privileged_conflict


def _add_link(record: dict[str, Any], source: str, source_id: Any) -> None:
    links = record.setdefault("identity_links", [])
    link = {"store": source, "user_id": str(source_id)}
    if link not in links:
        links.append(link)


def _has_grantflow_access(record: dict[str, Any]) -> bool:
    access = record.get("app_access") or {}
    levels = access.get("grantflow", []) if isinstance(access, dict) else []
    if isinstance(levels, str):
        levels = [levels]
    return isinstance(levels, list) and bool({str(x).casefold() for x in levels} & {"read", "all"})


def _plan() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    original, central = _read_users()
    username_counts = Counter(_norm(record.get("username")) for record in central)
    if not all(username_counts) or any(count > 1 for count in username_counts.values()):
        raise ValueError('Central usernames are missing or ambiguous; resolve before migration')
    email_counts = Counter(_norm(record.get("email")) for record in central if _norm(record.get("email")))
    source_rows: list[tuple[str, Path, str, str, dict[str, Any]]] = []
    source_summary: dict[str, Any] = {}
    for source, path, table, hash_column in SOURCES:
        rows = _read_source(source, path, table, hash_column)
        source_rows.extend((source, path, table, hash_column, row) for row in rows)
        source_summary[source] = {
            "rows": len(rows),
            "roles": dict(Counter(str(row.get("role") or "<missing>") for row in rows)),
            "active_approved": sum(_source_active(source, row) for row in rows),
            "hash_formats": dict(Counter(_hash_kind(row.get(hash_column)) for row in rows)),
        }

    # Existing central identifiers are provisioned once and versions are advanced once
    # to invalidate every pre-cutover token and session.
    changed_central = copy.deepcopy(central)
    for record in changed_central:
        if not record.get("identity_id"):
            record["identity_id"] = str(uuid.uuid4())
        if record.get("identity_migration_version") != 1:
            record["auth_version"] = int(record.get("auth_version", 1)) + 1
            record["identity_migration_version"] = 1

    central_by_email: dict[str, list[dict[str, Any]]] = defaultdict(list)
    central_by_username: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in changed_central:
        if _norm(record.get("email")):
            central_by_email[_norm(record.get("email"))].append(record)
        if _norm(record.get("username")):
            central_by_username[_norm(record.get("username"))].append(record)

    source_email_counts: dict[tuple[str, str], int] = Counter(
        (source, _norm(row.get("email")))
        for source, _, _, _, row in source_rows
        if _norm(row.get("email"))
    )
    source_username_counts: dict[tuple[str, str], int] = Counter(
        (source, _norm(row.get("username")))
        for source, _, _, _, row in source_rows
        if _norm(row.get("username"))
    )

    maps: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    imported = Counter()
    linked = Counter()
    password_formats = Counter()
    unusable_hashes = Counter()
    admin_review = 0

    for source, path, table, hash_column, row in source_rows:
        username = str(row.get("username") or "").strip()
        email = str(row.get("email") or "").strip()
        encoded = str(row.get(hash_column) or "")
        source_id = row.get("id")
        ref = _ref(source, source_id, username, email)
        email_key = _norm(email)
        username_key = _norm(username)
        same_source_email_ambiguous = bool(email_key and source_email_counts[(source, email_key)] > 1)
        same_source_username_ambiguous = bool(username_key and source_username_counts[(source, username_key)] > 1)
        email_matches = central_by_email.get(email_key, []) if email_key else []
        exact_matches = [candidate for candidate in email_matches if str(candidate.get("password") or "") == encoded and encoded]

        target = None
        reason = None
        mapped_identity_id = str(row.get("identity_id") or "").strip()
        mapped_matches = [candidate for candidate in changed_central if str(candidate.get("identity_id") or "") == mapped_identity_id]
        if mapped_identity_id and len(mapped_matches) == 1:
            target = mapped_matches[0]
            _add_link(target, source, source_id)
            linked[source] += 1
        elif mapped_identity_id:
            reason = 'durable_mapping_target_missing_or_ambiguous'
        elif same_source_email_ambiguous or same_source_username_ambiguous:
            reason = "duplicate_source_identity_claim"
        elif len(email_matches) == 1 and len(exact_matches) == 1:
            target = exact_matches[0]
            _add_link(target, source, source_id)
            linked[source] += 1
            if source in {'gfm', 'legacy_grantflow', 'legacy_devops_grantflow'}:
                if not _source_active(source, row):
                    denied = target.setdefault("app_access_denied", [])
                    if "grantflow" not in denied:
                        denied.append("grantflow")
                elif "grantflow" not in target.get("app_access_denied", []):
                    existing_access = target.setdefault("app_access", {})
                    if isinstance(existing_access, dict):
                        if not _has_grantflow_access(target):
                            existing_access["grantflow"] = ["read"] if _source_role(source, row)[0] == 'viewer' else ["read", "write"]
                        roles = target.setdefault("app_roles", {})
                        if isinstance(roles, dict) and "grantflow" not in roles:
                            grantflow_role, admin_conflict = _source_role(source, row)
                            roles["grantflow"] = grantflow_role
                            admin_review += int(admin_conflict)
        elif email_matches:
            reason = "email_conflict_or_ambiguous_match"
        elif username_key and central_by_username.get(username_key):
            reason = "username_collision_without_verified_identity_match"
        elif not username or not email:
            reason = "missing_username_or_email"
        elif not encoded:
            reason = "missing_password_hash"
        else:
            role, admin_conflict = _source_role(source, row)
            is_active = _source_active(source, row)
            identity_id = str(uuid.uuid4())
            hash_format = _hash_kind(encoded)
            imported_record = {
                "username": username,
                "email": email,
                "password": encoded,
                "role": "client",
                "approved": is_active,
                "is_active": bool(row.get("is_active", row.get("active", True))),
                "identity_id": identity_id,
                "auth_version": 2,
                "identity_migration_version": 1,
                "grantflow_only": True,
                "app_access": {"grantflow": ["read"] if role == 'viewer' else ["read", "write"]} if is_active else {},
                "app_roles": {"grantflow": "grant_writer" if admin_conflict else role},
                "identity_links": [{"store": source, "user_id": str(source_id)}],
                "password_reset_required": hash_format == "unsupported-or-missing",
            }
            if admin_conflict:
                admin_review += 1
            if hash_format == "unsupported-or-missing":
                unusable_hashes[source] += 1
            password_formats[(source, hash_format)] += 1
            changed_central.append(imported_record)
            central_by_email[email_key].append(imported_record)
            central_by_username[username_key].append(imported_record)
            imported[source] += 1
            target = imported_record

        if reason:
            conflicts.append({"source": source, "reference": ref, "reason": reason})
        if target:
            maps.append({
                "source": source,
                "db_path": str(path),
                "table": table,
                "source_user_id": source_id,
                "username": username,
                "email": email,
                "hash": encoded,
                "identity_id": target["identity_id"],
                "source_ref": ref,
                "kind": _hash_kind(encoded),
                "source_role": str(row.get("role") or ""),
                "source_active": _source_active(source, row),
                "admin_review": bool(row.get("role") == "admin"),
            })

    report = {
        "mode": "dry-run",
        "central_users": len(central),
        "central_roles": dict(Counter(str(record.get("role") or "<missing>") for record in central)),
        "central_approval": dict(Counter(str(record.get("approved", "<missing>")) for record in central)),
        "central_hash_formats": dict(Counter(_hash_kind(record.get("password")) for record in central)),
        "central_duplicate_email_groups": sum(count > 1 for count in email_counts.values()),
        "source_inventory": source_summary,
        "linked_by_exact_unique_email_and_hash": dict(linked),
        "imported_without_identity_collision": dict(imported),
        "mapped_rows": len(maps),
        "unresolved_conflicts": conflicts,
        "unusable_hashes_requiring_reset": dict(unusable_hashes),
        "legacy_admin_roles_downgraded_and_flagged": admin_review,
        "password_hashes_copied_exactly": {f"{source}:{kind}": count for (source, kind), count in password_formats.items()},
        "entitlement_policy": "Distinct imports retain approval restrictions and role-appropriate scopes. Unique email-plus-hash GFM links preserve prior access; inactive links carry an explicit app denial. Existing central credentials remain authoritative. Local admin roles require review.",
        "identity_match_policy": "Accounts link only when normalized email and exact stored hash uniquely match. Username-only matches and email/hash conflicts are reported, not merged.",
        "ownership_policy": "Existing source user IDs and application foreign keys remain unchanged; identity_migration_map and GFM users.identity_id preserve the central mapping.",
        "inactive_gfm_access_denied": sum("grantflow" in (record.get("app_access_denied") or []) for record in changed_central),
        "source_hashes_removed_from_gfm_projection": 0,
    }
    return changed_central, maps, report


def _apply(changed_central: list[dict[str, Any]], maps: list[dict[str, Any]]) -> Path:
    backup = _make_backup()
    connections: dict[Path, sqlite3.Connection] = {}
    try:
        for source, path, _, _ in SOURCES:
            if path.exists() and path not in connections:
                connection = sqlite3.connect(path)
                connection.execute("PRAGMA foreign_keys=ON")
                connections[path] = connection
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS identity_migration_map ("
                    "source TEXT NOT NULL, source_user_id TEXT NOT NULL, identity_id TEXT NOT NULL, "
                    "PRIMARY KEY(source, source_user_id))"
                )
                if source == "gfm":
                    columns = {row[1] for row in connection.execute('PRAGMA table_info("users")')}
                    if "identity_id" not in columns:
                        connection.execute('ALTER TABLE users ADD COLUMN identity_id VARCHAR(64)')
                    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_identity_id ON users(identity_id)")

        for mapping in maps:
            connection = connections[Path(mapping["db_path"])]
            connection.execute(
                "INSERT INTO identity_migration_map(source, source_user_id, identity_id) VALUES (?, ?, ?) "
                "ON CONFLICT(source, source_user_id) DO UPDATE SET identity_id=excluded.identity_id",
                (mapping["source"], str(mapping["source_user_id"]), mapping["identity_id"]),
            )
            if mapping["source"] == "gfm":
                connection.execute(
                    "UPDATE users SET identity_id=?, hashed_password=? WHERE id=?",
                    (mapping["identity_id"], SENTINEL_HASH, mapping["source_user_id"]),
                )

        _write_users(changed_central)
        for connection in connections.values():
            connection.commit()
        return backup
    except Exception:
        for connection in connections.values():
            connection.rollback()
            connection.close()
        connections.clear()
        _restore(backup)
        raise
    finally:
        for connection in connections.values():
            connection.close()


def _restore(backup: Path) -> None:
    manifest = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    allowed = {USERS_PATH.resolve(), *(path.resolve() for _, path, _, _ in SOURCES)}
    verified = []
    for item in manifest['files']:
        if item.get('status') == 'missing':
            continue
        destination, source = Path(item['source']).resolve(), Path(item['backup']).resolve()
        if destination not in allowed or source.parent != backup.resolve():
            raise ValueError('Backup manifest path is outside the configured stores')
        if hashlib.sha256(source.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Backup checksum mismatch')
        verified.append((source, destination))
    for source, destination in verified:
        if destination.suffix == '.db':
            with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as src, sqlite3.connect(destination) as dst:
                src.backup(dst)
        else:
            temporary = destination.with_suffix('.restore-tmp')
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)


def main() -> int:
    global ROOT, USERS_PATH, SOURCES
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT, help='Anthesis root; use a copied root for rehearsal')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="apply safe, unambiguous mappings")
    mode.add_argument("--rollback", type=Path, help="restore all stores from a backup directory")
    parser.add_argument("--report", type=Path, help="write sanitized JSON report outside the repository by default")
    args = parser.parse_args()
    original_root = ROOT
    ROOT = args.root.resolve()
    USERS_PATH = ROOT / 'users.json'
    SOURCES = [(source, ROOT / path.relative_to(original_root), table, column) for source, path, table, column in SOURCES]
    if (args.apply or args.rollback) and ROOT == original_root:
        import socket
        for port in (5000, 8001):
            with socket.socket() as probe:
                probe.settimeout(1)
                if probe.connect_ex(('127.0.0.1', port)) == 0:
                    parser.error(f'Stop Anthesis and GFM writers before changing stores (port {port} is active)')
    default_report = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "Anthesis" / "identity-cutover-report.json"
    report_path = args.report or default_report

    if args.rollback:
        _restore(args.rollback.resolve())
        print(json.dumps({"mode": "rollback", "restored_from": str(args.rollback.resolve())}, indent=2))
        return 0

    changed_central, maps, report = _plan()
    report["mode"] = "apply" if args.apply else "dry-run"
    if args.apply:
        backup = _apply(changed_central, maps)
        report["backup_directory"] = str(backup)
        report["mapped_rows"] = len(maps)
        report["source_hashes_removed_from_gfm_projection"] = sum(m["source"] == "gfm" for m in maps)
    report["report_path"] = str(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
