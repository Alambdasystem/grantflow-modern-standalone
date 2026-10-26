"""A durable import hold prevents replay through every external automation entry."""
from fastapi import HTTPException
from models.auth_models import MigrationSafety


async def held(db):
    state=await db.get(MigrationSafety,1)
    return bool(state and state.external_jobs_paused)


async def require_released(db):
    if await held(db):
        raise HTTPException(409,'Imported external automation is paused pending operator review')
