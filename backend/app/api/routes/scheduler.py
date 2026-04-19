"""
api/routes/scheduler.py

GET  /api/v1/scheduler/status           — job status and next run times
POST /api/v1/scheduler/trigger/jira     — manually trigger Jira poll now
POST /api/v1/scheduler/trigger/sharepoint — manually trigger SP poll now
POST /api/v1/scheduler/pause            — pause all jobs
POST /api/v1/scheduler/resume           — resume all jobs
"""

import logging
from fastapi import APIRouter, HTTPException
from app.services.scheduler.ticket_scheduler import (
    _scheduler,
    run_jira_scheduler_job,
    run_sharepoint_scheduler_job,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/scheduler", tags=["scheduler"])


@router.get("/status")
def scheduler_status():
    if not _scheduler:
        return {"running": False, "jobs": [], "message": "Scheduler not started."}
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id":            job.id,
            "name":          job.name,
            "next_run_time": str(job.next_run_time) if job.next_run_time else "paused",
        })
    return {"running": _scheduler.running, "jobs": jobs}


@router.post("/trigger/jira")
def trigger_jira_now():
    """Manually trigger the Jira polling job immediately."""
    try:
        run_jira_scheduler_job()
        return {"status": "triggered", "source": "jira"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/trigger/sharepoint")
def trigger_sharepoint_now():
    """Manually trigger the SharePoint Local polling job immediately."""
    try:
        run_sharepoint_scheduler_job()
        return {"status": "triggered", "source": "sharepoint_local"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/pause")
def pause_scheduler():
    if not _scheduler or not _scheduler.running:
        raise HTTPException(status_code=400, detail="Scheduler is not running.")
    _scheduler.pause()
    return {"status": "paused"}


@router.post("/resume")
def resume_scheduler():
    if not _scheduler or not _scheduler.running:
        raise HTTPException(status_code=400, detail="Scheduler is not running.")
    _scheduler.resume()
    return {"status": "resumed"}
