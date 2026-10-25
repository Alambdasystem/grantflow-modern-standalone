"""
Startup seeding — runs during lifespan startup.
1. Seeds portal credentials from env vars (grants_gov etc.).
3. Wired into new-account creation so any fresh install is ready to use.
"""
import base64
import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from config import settings


def _b64enc(s: str) -> str:
    return base64.b64encode(s.encode()).decode() if s else ""


async def seed_admin_user(db: AsyncSession) -> bool:
    """Create the default admin account if no admin users exist. Returns True if created."""
    from models.models import User, UserRole, Organization

    result = await db.execute(
        select(func.count()).select_from(User).where(User.role == UserRole.admin)
    )
    count = result.scalar() or 0
    if count > 0:
        return False  # admin already exists

    if not all([settings.DEFAULT_ADMIN_USERNAME, settings.DEFAULT_ADMIN_EMAIL, settings.DEFAULT_ADMIN_PASSWORD]):
        return False
    username = settings.DEFAULT_ADMIN_USERNAME
    email = settings.DEFAULT_ADMIN_EMAIL
    password = settings.DEFAULT_ADMIN_PASSWORD
    full_name = settings.DEFAULT_ADMIN_FULLNAME or "Configured legacy administrator"

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = User(
        username=username,
        email=email,
        hashed_password=hashed,
        full_name=full_name,
        role=UserRole.admin,
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    await db.commit()
    print(f"[seed] Created admin user: {username} ({email})")
    return True


async def seed_portal_credentials(db: AsyncSession):
    """Write env-configured portal credentials to DB (won't overwrite existing)."""
    from models.models import PortalCredential

    PORTAL_ENVS = [
        ("grants_gov",        "Grants.gov",              "https://apply07.grants.gov/apply/login.faces",   "username_password", settings.GRANTS_GOV_USERNAME,        settings.GRANTS_GOV_PASSWORD),
        ("sam_gov",           "SAM.gov",                 "https://sam.gov/profile/details",                "username_password", settings.SAM_GOV_USERNAME,           settings.SAM_GOV_PASSWORD),
        ("justgrants",        "JustGrants (DOJ)",        "https://justgrants.usdoj.gov",                   "username_password", settings.JUSTGRANTS_USERNAME,         settings.JUSTGRANTS_PASSWORD),
        ("foundation_center", "Candid / Foundation Center", "https://candid.org/login",                   "username_password", settings.FOUNDATION_CENTER_USERNAME,  settings.FOUNDATION_CENTER_PASSWORD),
    ]

    for portal_key, portal_name, portal_url, ctype, username, password in PORTAL_ENVS:
        if not username and not password:
            continue

        result = await db.execute(
            select(PortalCredential).where(PortalCredential.portal_key == portal_key)
        )
        cred = result.scalar_one_or_none()
        if not cred:
            cred = PortalCredential(portal_key=portal_key)
            db.add(cred)

        cred.portal_name = portal_name
        cred.portal_url = portal_url
        cred.credential_type = ctype

        if username and not cred.username:
            cred.username = username
        if password and not cred.password_b64:
            cred.password_b64 = _b64enc(password)

    await db.commit()


async def after_user_registration(user_id: int, db: AsyncSession):
    """
    Called after a new GrantFlow user account is created.
    Currently a no-op — portal credentials are system-level and visible to all users.
    Extend here if you ever add per-user portal credential scoping.
    """
    pass


async def _migrate_organizations(db: AsyncSession):
    """Add new Organization columns to existing SQLite databases (idempotent)."""
    new_columns = [
        ("uei",                    "VARCHAR(20)"),
        ("city",                   "VARCHAR(100)"),
        ("state",                  "VARCHAR(50)"),
        ("zip_code",               "VARCHAR(20)"),
        ("country",                "VARCHAR(50) DEFAULT 'US'"),
        ("congressional_district", "VARCHAR(10)"),
        ("aor_first_name",         "VARCHAR(100)"),
        ("aor_last_name",          "VARCHAR(100)"),
        ("aor_title",              "VARCHAR(200)"),
        ("aor_phone",              "VARCHAR(50)"),
        ("aor_email",              "VARCHAR(255)"),
    ]
    # Get existing columns via PRAGMA
    result = await db.execute(__import__("sqlalchemy").text("PRAGMA table_info(organizations)"))
    existing = {row[1] for row in result.fetchall()}
    for col_name, col_def in new_columns:
        if col_name not in existing:
            try:
                await db.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE organizations ADD COLUMN {col_name} {col_def}"
                    )
                )
                print(f"[migrate] Added organizations.{col_name}")
            except Exception as exc:
                print(f"[migrate] Could not add {col_name}: {exc}")
    await db.commit()


async def _migrate_grants(db: AsyncSession):
    """Add grant_type and foundation_id columns to existing grants table (idempotent)."""
    from sqlalchemy import text
    result = await db.execute(text("PRAGMA table_info(grants)"))
    existing = {row[1] for row in result.fetchall()}
    for col_name, col_def in [
        ("grant_type",              "VARCHAR(50) DEFAULT 'federal'"),
        ("foundation_id",           "INTEGER"),
        ("requirements_detail",     "JSON"),
        ("requirements_fetched_at", "DATETIME"),
    ]:
        if col_name not in existing:
            try:
                await db.execute(text(f"ALTER TABLE grants ADD COLUMN {col_name} {col_def}"))
                print(f"[migrate] Added grants.{col_name}")
            except Exception as exc:
                print(f"[migrate] Could not add grants.{col_name}: {exc}")
    await db.commit()


async def _migrate_grant_applications(db: AsyncSession):
    """Add new renewal/tracking columns to grant_applications (idempotent)."""
    from sqlalchemy import text
    result = await db.execute(text("PRAGMA table_info(grant_applications)"))
    existing = {row[1] for row in result.fetchall()}
    for col_name, col_def in [
        ("source_type",           "VARCHAR(50) DEFAULT 'federal'"),
        ("grant_period_start",    "DATETIME"),
        ("grant_period_end",      "DATETIME"),
        ("report_due_dates",      "JSON"),
        ("year_number",           "INTEGER DEFAULT 1"),
        ("parent_application_id", "INTEGER"),
        ("is_multi_year",         "BOOLEAN DEFAULT 0"),
    ]:
        if col_name not in existing:
            try:
                await db.execute(text(f"ALTER TABLE grant_applications ADD COLUMN {col_name} {col_def}"))
                print(f"[migrate] Added grant_applications.{col_name}")
            except Exception as exc:
                print(f"[migrate] Could not add grant_applications.{col_name}: {exc}")
    await db.commit()


async def run_all_seeds():
    """Entry point called from main.py lifespan startup."""
    from db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await _migrate_organizations(db)
        await _migrate_grants(db)
        await _migrate_grant_applications(db)
        await seed_portal_credentials(db)
