"""Migration adapter — reads from legacy grant_flow.db and users.json, imports into GrantFlow Modern."""
import sqlite3
import json
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))

from sqlalchemy.ext.asyncio import AsyncSession
from db.database import AsyncSessionLocal, init_db
from models.models import Grant, GrantStatus, User, UserRole, Organization, Document
from auth.jwt_handler import hash_password
from config import settings
from datetime import datetime, timezone


WYF_PROFILE = {'name': 'Synthetic Example Organization', 'email': 'organization@example.invalid', 'phone': '', 'website': 'https://example.invalid', 'founded_year': '2000', 'description': 'Synthetic legacy import example', 'mission': 'Synthetic education mission', 'capabilities': 'Synthetic education programs', 'categories': ['Education'], 'eligibility_tags': ['nonprofit']}

COUNTY_CONNECTIONS_GRANT = {'title': 'Synthetic Example Grant', 'description': 'Synthetic historical example', 'funding_agency': 'Synthetic agency', 'amount': 20000.0, 'eligibility': 'Synthetic nonprofit', 'category': 'Education', 'source_url': 'https://example.invalid/grant'}


def _resolve_legacy_path(configured_path: str) -> str:
    if os.path.isabs(configured_path):
        return configured_path

    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    migration_dir = os.path.abspath(os.path.dirname(__file__))
    grantflow_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    candidates = [
        os.path.abspath(configured_path),
        os.path.abspath(os.path.join(migration_dir, configured_path)),
        os.path.abspath(os.path.join(grantflow_root, configured_path)),
        os.path.abspath(os.path.join(workspace_root, configured_path)),
        os.path.abspath(os.path.join(workspace_root, os.path.basename(configured_path))),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[0]


async def ensure_wyf_profile(db: AsyncSession) -> Organization:
    from sqlalchemy import select

    result = await db.execute(
        select(Organization).where(Organization.name == WYF_PROFILE["name"]).limit(1)
    )
    org = result.scalar_one_or_none()
    if org:
        changed = False
        for field in (
            "email", "phone", "website", "founded_year", "description", "mission", "capabilities"
        ):
            value = WYF_PROFILE[field]
            if not getattr(org, field):
                setattr(org, field, value)
                changed = True
        if not org.categories:
            org.categories = WYF_PROFILE["categories"]
            changed = True
        if not org.eligibility_tags:
            org.eligibility_tags = WYF_PROFILE["eligibility_tags"]
            changed = True
        if not org.profile_complete:
            org.profile_complete = True
            changed = True
        if changed:
            await db.flush()
        return org

    org = Organization(
        name=WYF_PROFILE["name"],
        email=WYF_PROFILE["email"],
        phone=WYF_PROFILE["phone"],
        website=WYF_PROFILE["website"],
        founded_year=WYF_PROFILE["founded_year"],
        description=WYF_PROFILE["description"],
        mission=WYF_PROFILE["mission"],
        capabilities=WYF_PROFILE["capabilities"],
        categories=WYF_PROFILE["categories"],
        eligibility_tags=WYF_PROFILE["eligibility_tags"],
        profile_complete=True,
        meta={"seeded_from": "legacy_wyf_profile"},
    )
    db.add(org)
    await db.flush()
    return org


async def sync_legacy_company_profile(db: AsyncSession, organization: Organization) -> None:
    db_path = _resolve_legacy_path(settings.LEGACY_GRANT_DB)
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT name, ein, business_address, corporate_address, phone, email, website, founded_year,
                   structure, description, mission, naics_codes, sic_codes, capabilities, client_since
            FROM companies WHERE name = ? LIMIT 1
            """,
            (organization.name,),
        )
        row = cursor.fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        conn.close()

    if not row:
        return

    data = dict(row)
    organization.ein = data.get("ein") or organization.ein
    organization.phone = data.get("phone") or organization.phone
    organization.email = data.get("email") or organization.email
    organization.website = data.get("website") or organization.website
    organization.founded_year = data.get("founded_year") or organization.founded_year
    organization.description = data.get("description") or organization.description
    organization.mission = data.get("mission") or organization.mission
    organization.capabilities = data.get("capabilities") or organization.capabilities
    if not organization.address:
        organization.address = data.get("business_address") or data.get("corporate_address")
    meta = dict(organization.meta or {})
    meta.update(
        {
            "legacy_business_address": data.get("business_address"),
            "legacy_corporate_address": data.get("corporate_address"),
            "legacy_structure": data.get("structure"),
            "legacy_naics_codes": data.get("naics_codes"),
            "legacy_sic_codes": data.get("sic_codes"),
            "legacy_client_since": data.get("client_since"),
        }
    )
    organization.meta = meta
    organization.profile_complete = True
    await db.flush()


async def migrate_legacy_knowledge_documents(db: AsyncSession, organization: Organization) -> int:
    db_path = _resolve_legacy_path(settings.LEGACY_GRANT_DB)
    if not os.path.exists(db_path):
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT organization_name, title, filename, file_type, file_path, summary, extracted_text
            FROM grant_knowledge_documents
            WHERE organization_name = ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (organization.name,),
        )
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()

    from sqlalchemy import select

    count = 0
    for row in rows:
        existing = await db.execute(
            select(Document).where(
                Document.organization_id == organization.id,
                Document.original_filename == row["filename"],
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            continue

        db.add(
            Document(
                organization_id=organization.id,
                filename=row["filename"] or row["title"] or "legacy-document",
                original_filename=row["filename"] or row["title"] or "legacy-document",
                file_path=row["file_path"],
                content_type=row["file_type"] or "legacy",
                document_type="organization_profile",
                ai_summary=row["summary"],
                extracted_text=row["extracted_text"],
                tags=["legacy", "knowledge-base", "wyf"],
            )
        )
        count += 1

    if count:
        await db.flush()
    return count


async def ensure_seed_grants(db: AsyncSession) -> None:
    from sqlalchemy import select

    existing = await db.execute(
        select(Grant).where(Grant.title == COUNTY_CONNECTIONS_GRANT["title"]).limit(1)
    )
    if existing.scalar_one_or_none():
        return

    db.add(
        Grant(
            title=COUNTY_CONNECTIONS_GRANT["title"],
            description=COUNTY_CONNECTIONS_GRANT["description"],
            funding_agency=COUNTY_CONNECTIONS_GRANT["funding_agency"],
            amount=COUNTY_CONNECTIONS_GRANT["amount"],
            eligibility=COUNTY_CONNECTIONS_GRANT["eligibility"],
            category=COUNTY_CONNECTIONS_GRANT["category"],
            source_url=COUNTY_CONNECTIONS_GRANT["source_url"],
            portal_key="grants_gov",
            status=GrantStatus.active,
            tags=["youth", "literacy", "summer", "mentoring"],
            requirements=["nonprofit", "youth-serving", "summer-enrichment"],
            ai_summary="High-fit starter opportunity for WYF-aligned youth enrichment programming.",
        )
    )
    await db.flush()


async def migrate_grants_from_legacy(db: AsyncSession) -> int:
    """Import grants from the legacy grant_flow.db SQLite database."""
    db_path = _resolve_legacy_path(settings.LEGACY_GRANT_DB)
    if not os.path.exists(db_path):
        print(f"[migration] Legacy DB not found at {db_path}, skipping grant migration.")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM grant_opportunities LIMIT 2000")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        print("[migration] grant_opportunities table not found in legacy DB.")
        conn.close()
        return 0

    count = 0
    for row in rows:
        from sqlalchemy import select
        existing = await db.execute(
            select(Grant).where(Grant.legacy_id == row["id"])
        )
        if existing.scalar_one_or_none():
            continue  # Already imported

        deadline = None
        if row["deadline"]:
            try:
                deadline = datetime.fromisoformat(str(row["deadline"]).replace("Z", "+00:00"))
            except Exception:
                pass

        grant = Grant(
            legacy_id=row["id"],
            title=row["title"] or "Untitled Grant",
            description=row["description"],
            funding_agency=row["funding_agency"],
            amount=row["amount"],
            deadline=deadline,
            deadline_str=str(row["deadline"]) if row["deadline"] else None,
            eligibility=row["eligibility"],
            category=row["category"],
            source_url=row["source_url"],
            status=GrantStatus.active,
            tags=[],
            requirements=[],
        )
        db.add(grant)
        count += 1

    await db.commit()
    conn.close()
    print(f"[migration] Imported {count} grants from legacy DB.")
    return count


async def migrate_users_from_legacy(db: AsyncSession) -> int:
    """Import approved users from the legacy users.json."""
    users_path = _resolve_legacy_path(settings.LEGACY_USERS_JSON)
    if not os.path.exists(users_path):
        print(f"[migration] Legacy users.json not found at {users_path}, skipping.")
        return 0

    with open(users_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    users_dict = data if isinstance(data, dict) else {
        u.get("username"): u for u in data if isinstance(u, dict) and u.get("username")
    }

    count = 0
    from sqlalchemy import select
    wyf_org = await ensure_wyf_profile(db)
    for username, record in users_dict.items():
        existing = await db.execute(select(User).where(User.username == username))
        existing_user = existing.scalar_one_or_none()
        email = record.get("email") or f"{username}@grantflow.local"
        existing_by_email = await db.execute(select(User).where(User.email == email))
        email_user = existing_by_email.scalar_one_or_none()

        # Equal email is not evidence that two historical usernames are the
        # same identity. Never move an existing account into the seeded org.
        if email_user and (not existing_user or email_user.id != existing_user.id):
            raise ValueError('Legacy email collision requires a reviewed identity mapping')

        role = UserRole.admin if record.get("role") == "admin" else UserRole.grant_writer
        organization_id = None
        preferences = {}
        if username == "wyf_admin" or record.get("grantflow_only"):
            organization_id = wyf_org.id
            preferences = {
                "track": record.get("track"),
                "grantflow_only": bool(record.get("grantflow_only")),
                "mailbox": {
                    "enabled": bool(record.get("mailbox_enabled")),
                    "email": record.get("mailbox_email"),
                    "username": record.get("mailbox_username"),
                    "auth_mode": record.get("mailbox_auth_mode"),
                },
                "app_access": record.get("app_access") or {},
            }

        target_user = existing_user
        if target_user:
            changed = False
            if organization_id and target_user.organization_id != organization_id:
                target_user.organization_id = organization_id
                changed = True
            merged_preferences = dict(target_user.preferences or {})
            if preferences:
                merged_preferences.update(preferences)
                target_user.preferences = merged_preferences
                changed = True
            if not target_user.full_name and (record.get("full_name") or record.get("name")):
                target_user.full_name = record.get("full_name") or record.get("name")
                changed = True
            if changed:
                count += 1
            continue

        user = User(
            username=username,
            email=email,
            hashed_password=record.get("password") or "!central-identity-only!",
            full_name=record.get("full_name") or record.get("name"),
            role=role,
            is_approved=bool(record.get("approved", True)),
            organization_id=organization_id,
            preferences=preferences,
        )
        db.add(user)
        count += 1

    await db.commit()
    print(f"[migration] Imported {count} users from legacy users.json.")
    return count


async def ensure_default_admin(db: AsyncSession) -> None:
    """Legacy opt-in only: requires explicit runtime credentials."""
    from startup_seed import seed_admin_user
    await seed_admin_user(db)


async def run_full_migration():
    await init_db()
    async with AsyncSessionLocal() as db:
        wyf_org = await ensure_wyf_profile(db)
        await sync_legacy_company_profile(db, wyf_org)
        await migrate_grants_from_legacy(db)
        print("[migration] User identity import is managed by the Anthesis identity migration command.")
        await migrate_legacy_knowledge_documents(db, wyf_org)
        await ensure_seed_grants(db)
        await db.commit()
    print("[migration] Migration complete.")


if __name__ == "__main__":
    asyncio.run(run_full_migration())
