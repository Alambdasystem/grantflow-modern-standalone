"""A durable import hold prevents replay through every external automation entry."""
from fastapi import HTTPException
from models.auth_models import MigrationSafety


async def held(db):
    state=await db.get(MigrationSafety,1)
    return bool(state and state.external_jobs_paused)


def public_discovery(job):
    """Only new server-stamped public searches may run during the import hold.

    Old/imported jobs, renewals and portal operations remain held. Request
    parameters cannot supply this marker or attach a portal/application.
    """
    return bool(job and job.job_type == 'scrape'
                and (job.result or {}).get('public_discovery_v1') is True
                and not job.application_id and not job.portal_key and not job.portal_url)


async def require_released(db):
    if await held(db):
        raise HTTPException(409,'Imported external automation is paused pending operator review')
