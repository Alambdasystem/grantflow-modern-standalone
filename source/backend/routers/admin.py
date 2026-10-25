"""Admin-only maintenance endpoints: data quality fixes, archival, bulk ops."""
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.database import get_db
from models.models import Grant, GrantApplication, GrantStatus
from auth.jwt_handler import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

_REPLACEMENT_CHAR = "�"  # Unicode replacement character stored when em-dash bytes weren't valid UTF-8


def _fix_title_encoding(title: str) -> str:
    """Replace Unicode replacement characters used as title separators with em-dash."""
    return title.replace(_REPLACEMENT_CHAR, "—")  # U+FFFD -> em-dash


@router.post("/fix-encoding")
async def fix_encoding(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """Fix corrupted em-dash characters in grant and application titles."""
    fixed_grants = 0
    fixed_apps = 0

    grants_result = await db.execute(select(Grant))
    for grant in grants_result.scalars().all():
        if grant.title and _REPLACEMENT_CHAR in grant.title:
            grant.title = _fix_title_encoding(grant.title)
            fixed_grants += 1
        if grant.description and _REPLACEMENT_CHAR in grant.description:
            grant.description = _fix_title_encoding(grant.description)

    apps_result = await db.execute(select(GrantApplication))
    for app in apps_result.scalars().all():
        if app.title and _REPLACEMENT_CHAR in app.title:
            app.title = _fix_title_encoding(app.title)
            fixed_apps += 1

    await db.commit()
    return {
        "fixed": fixed_grants + fixed_apps,
        "fixed_grants": fixed_grants,
        "fixed_applications": fixed_apps,
    }


@router.post("/archive-expired-grants")
async def archive_expired_grants(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """Set status=archived on grants whose deadline is in the past."""
    today_str = date.today().isoformat()

    result = await db.execute(
        select(Grant).where(
            Grant.status == GrantStatus.active,
            Grant.deadline.isnot(None),
            Grant.deadline < today_str,
        )
    )
    expired = result.scalars().all()

    for grant in expired:
        grant.status = GrantStatus.archived

    await db.commit()
    return {
        "archived": len(expired),
        "grant_ids": [g.id for g in expired],
    }
