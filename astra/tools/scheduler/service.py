"""Scheduler service for managing automated tasks."""

import logging
from typing import Any

# Try to import psutil for resource guard, handle if missing
try:
    import psutil
except ImportError:
    psutil = None

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from astra.config import Config, get_config

logger = logging.getLogger(__name__)

# --- Singleton accessor is deprecated but kept for backward compatibility helper ---
_SERVICE_INSTANCE = None


def get_scheduler_service() -> "SchedulerService":
    """Get or create the global scheduler service instance."""
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = SchedulerService(get_config())
    return _SERVICE_INSTANCE


class SchedulerService:
    """Service to manage APScheduler instance with resource awareness."""

    def __init__(self, config: Config):
        self._config = config
        self._scheduler_config = config.scheduler
        self._db_path = (
            f"sqlite:///{self._scheduler_config.db_path}"
            if not self._scheduler_config.db_path.startswith("sqlite:///")
            else self._scheduler_config.db_path
        )

        self._job_stores = {"default": SQLAlchemyJobStore(url=self._db_path)}

        # Configure scheduler with coalescing and grace time defaults
        job_defaults = {
            "coalesce": self._scheduler_config.coalesce,
            "max_instances": 1,
            "misfire_grace_time": self._scheduler_config.misfire_grace_time,
        }

        self._scheduler = AsyncIOScheduler(jobstores=self._job_stores, job_defaults=job_defaults)

        # O(1) cache for project jobs: project_path -> set(job_ids)
        self._project_jobs_cache: dict[str, set[str]] = {}

        # In-memory status tracking: job_id -> {"status": "success"|"failed", "last_run": timestamp}
        self._job_status_cache: dict[str, dict[str, Any]] = {}

        self._started = False

        # Register event listeners
        self._scheduler.add_listener(self._on_job_completed, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

        # Start if enabled
        if self._scheduler_config.enabled:
            self.start()

    def start(self):
        """Start the scheduler if not already started."""
        if not self._started and self._scheduler_config.enabled:
            # Rebuild cache on start
            self._rebuild_cache()
            self._scheduler.start()
            self._started = True
            logger.info(f"Scheduler service started (DB: {self._scheduler_config.db_path})")

    def stop(self):
        """Stop the scheduler."""
        if self._started:
            self._scheduler.shutdown()
            self._started = False
            logger.info("Scheduler service stopped")

    def _rebuild_cache(self):
        """Rebuild the O(1) project jobs cache."""
        self._project_jobs_cache = {}
        for job in self._scheduler.get_jobs():
            if len(job.args) >= 2:
                project = job.args[1]
                if project not in self._project_jobs_cache:
                    self._project_jobs_cache[project] = set()
                self._project_jobs_cache[project].add(job.id)

    def _on_job_completed(self, event):
        """Handle job completion events."""
        job_id = event.job_id
        status = "failed" if event.exception else "success"

        # Update status cache
        self._job_status_cache[job_id] = {
            "status": status,
            "last_run": event.scheduled_run_time.isoformat()
            if event.scheduled_run_time
            else "manual_or_unknown",
            "error": str(event.exception) if event.exception else None,
        }

        # Auto-Disable Logic: Check consecutive failures if needed
        # (Simplified: just log for now, can be expanded to proper auto-disable in future)
        if status == "failed":
            logger.warning(f"Job {job_id} failed: {event.exception}")

    def schedule_job(
        self,
        command: str,
        cron_expression: str,
        project_path: str,
        description: str = "",
        job_id: str | None = None,
    ) -> str:
        """Schedule a shell command job."""
        if self._scheduler_config.enabled and not self._started:
            self.start()

        trigger = CronTrigger.from_crontab(cron_expression)

        # Store cron expression in kwargs for retrieval
        job_kwargs = {"cron_expression": cron_expression}

        job = self._scheduler.add_job(
            execute_job_wrapper,
            trigger=trigger,
            id=job_id,
            args=[
                command,
                project_path,
                self._scheduler_config.resource_guard_enabled,
                self._scheduler_config.max_memory_percent,
            ],
            kwargs=job_kwargs,
            name=description or command,
            replace_existing=True,
            jobstore="default",
        )

        # Update cache
        if project_path not in self._project_jobs_cache:
            self._project_jobs_cache[project_path] = set()
        self._project_jobs_cache[project_path].add(job.id)

        logger.info(f"Scheduled job {job.id}: {command} ({cron_expression})")
        return job.id

    def list_jobs(self, project_path: str) -> list[dict[str, Any]]:
        """List active jobs for the given project using O(1) lookup cache."""
        target_ids = self._project_jobs_cache.get(project_path, set())
        jobs = []

        for job in self._scheduler.get_jobs():
            if job.id in target_ids:
                status_info = self._job_status_cache.get(job.id, {"status": "pending"})
                next_run = job.next_run_time.isoformat() if job.next_run_time else "Paused"

                # Retrieve stored cron expression
                cron_expression = job.kwargs.get("cron_expression", "") if job.kwargs else ""

                jobs.append(
                    {
                        "id": job.id,
                        "name": job.name,
                        "command": job.args[0],
                        "next_run": next_run,
                        "cron_expression": cron_expression,
                        "project": job.args[1],
                        "last_status": status_info["status"],
                        "last_error": status_info.get("error"),
                    }
                )
        return jobs

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job by ID."""
        try:
            # We need to find the project to update cache before removing
            job = self._scheduler.get_job(job_id)
            if job and len(job.args) >= 2:
                project = job.args[1]
                if project in self._project_jobs_cache:
                    self._project_jobs_cache[project].discard(job_id)

            self._scheduler.remove_job(job_id)
            return True
        except Exception:
            return False

    async def run_job_now(self, job_id: str) -> str:
        """Manually trigger a job immediately."""
        job = self._scheduler.get_job(job_id)
        if not job:
            return f"❌ Job {job_id} not found."

        # Execute wrapper directly
        try:
            # Extract args: command, project_path, resource_guard, max_mem
            # Note: modify_job(next_run_time=now) schedules it, but we want to await the result?
            # APScheduler runs in background. If we want immediate result, we should run the function directly.
            # But that won't update job history in APScheduler cleanly unless we rely on the listener?
            # Let's run the function directly for immediate feedback.

            command, project_path, rg, max_mem = job.args
            result = await execute_job_wrapper(command, project_path, rg, max_mem)
            return f"✅ Job triggered manually:\n{result}"
        except Exception as e:
            return f"❌ Failed to run job: {e}"

    def health_check(self) -> dict[str, Any]:
        """Perform a self-diagnosis."""
        db_ok = True
        count = 0
        try:
            # Verify DB connection/jobstore
            if self._scheduler.running:
                # Just counting jobs checks DB connectivity
                count = len(self._scheduler.get_jobs())
        except Exception:
            db_ok = False

        return {
            "status": "healthy" if self._started and db_ok else "degraded",
            "running": self._started,
            "jobs_count": count,
            "resource_guard": "enabled"
            if self._scheduler_config.resource_guard_enabled
            else "disabled",
            "db_connected": db_ok,
        }


async def execute_job_wrapper(
    command: str,
    project_path: str,
    resource_guard: bool = True,
    max_memory_percent: int = 90,
    **kwargs: Any,
):
    """Wrapper to execute a job with resource guards.

    This function must be picklable and available in the module scope.
    """
    # --- Resource Guard ---
    if resource_guard and psutil:
        mem = psutil.virtual_memory()
        if mem.percent > max_memory_percent:
            msg = f"⚠️ Job execution skipped: System memory {mem.percent}% > {max_memory_percent}%"
            logger.warning(f"{msg} | Command: {command}")
            return msg

    logger.info(f"Executing scheduled job: {command} in {project_path}")
    return await _async_execute(command, project_path)


async def _async_execute(command: str, project_path: str):
    """Execute the command using the ShellTool."""
    # Lazy import to avoid circular dependencies and runtime overhead
    from astra.tools.shell import ShellExecutor

    try:
        # Instantiate the tool (cwd is passed to execute, not init)
        tool = ShellExecutor()

        # Execute the command.
        # Note: We explicitly set safe_to_run=True because cron jobs are
        # pre-authorized by the admin who scheduled them.
        result = await tool.execute(command, cwd=project_path)

        logger.info(f"Job execution result for '{command}': {result}")
        return result
    except Exception as e:
        logger.error(f"Job execution failed for '{command}': {e}")
        return f"Error: {str(e)}"
