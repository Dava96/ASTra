"""Cron scheduler tool."""

import logging
from typing import Any

from astra.core.tools import BaseTool
from astra.tools.scheduler.service import get_scheduler_service

logger = logging.getLogger(__name__)


class CronTool(BaseTool):
    """Tool for scheduling automated cron jobs."""

    name = "cron_scheduler"
    description = "Schedule, list, and manage automated cron jobs for the project."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["schedule", "list", "cancel", "run_now", "health"],
                "description": "Action to perform",
            },
            "cron": {
                "type": "string",
                "description": "Cron expression (e.g., '0 0 * * *') for 'schedule' action",
            },
            "command": {
                "type": "string",
                "description": "Shell command to execute for 'schedule' action",
            },
            "description": {"type": "string", "description": "Description of the job"},
            "job_id": {"type": "string", "description": "Job ID for 'cancel' or 'run_now' action"},
            "project_path": {
                "type": "string",
                "description": "Project root path (optional, defaults to current working dir)",
            },
        },
        "required": ["action"],
    }

    def __init__(self):
        self._service = get_scheduler_service()

    async def execute(self, action: str, **kwargs: Any) -> Any:
        try:
            if action == "schedule":
                return self._schedule(kwargs)
            elif action == "list":
                return self._list(kwargs)
            elif action == "cancel":
                return self._cancel(kwargs)
            elif action == "run_now":
                return await self._run_now(kwargs)
            elif action == "health":
                return self._health(kwargs)
            else:
                return f"❌ Unknown action: {action}"
        except Exception as e:
            return f"❌ Error executing cron action: {e}"

    def _schedule(self, kwargs: dict) -> str:
        cron = kwargs.get("cron")
        command = kwargs.get("command")
        desc = kwargs.get("description", "")
        project_path = kwargs.get("project_path") or "."

        if not cron or not command:
            return "❌ 'cron' and 'command' are required for schedule action."

        try:
            job_id = self._service.schedule_job(
                command=command, cron_expression=cron, project_path=project_path, description=desc
            )
            return f"✅ Scheduled job '{command}' (ID: {job_id}) at '{cron}'"
        except Exception as e:
            return f"❌ Failed to schedule job: {e} (Verify cron expression)"

    def _list(self, kwargs: dict) -> str:
        project_path = kwargs.get("project_path") or "."
        jobs = self._service.list_jobs(project_path)

        if not jobs:
            return "No active cron jobs found for this project."

        try:
            from cron_descriptor import get_description
        except ImportError:
            def get_description(cron):
                return "Install 'cron-descriptor' for human-readable descriptions"

        lines = ["📅 **Active Cron Jobs**"]
        for job in jobs:
            status_icon = (
                "🟢"
                if job.get("last_status") == "success"
                else "🔴"
                if job.get("last_status") == "failed"
                else "⚪"
            )

        lines = ["📅 **Active Cron Jobs**"]
        for job in jobs:
            status_icon = (
                "🟢"
                if job.get("last_status") == "success"
                else "🔴"
                if job.get("last_status") == "failed"
                else "⚪"
            )

            # Get description
            cron_expr = job.get("cron_expression", "")
            try:
                if cron_expr:
                    desc = get_description(cron_expr)
                else:
                    desc = "Schedule available but expression missing"
            except Exception:
                desc = "Invalid cron expression"

            # Format:
            # - **ID: <id>** | <name> <icon>
            #   Schedule: "<desc>" (`<cron>`)
            #   Command: `<cmd>`
            #   Next: <next>

            lines.append(f"- **ID: {job['id']}** | {job['name']} {status_icon}")
            if cron_expr:
                 lines.append(f"  Schedule: \"{desc}\" (`{cron_expr}`)")
            else:
                 lines.append(f"  Schedule: {job.get('next_run', 'Unknown')}")

            lines.append(f"  Command: `{job['command']}`")
            lines.append(f"  Next Run: {job['next_run']}")

            if job.get("last_status") == "failed":
                lines.append(f"  Last Error: {job.get('last_error')}")

        return "\n".join(lines)

    def _cancel(self, kwargs: dict) -> str:
        job_id = kwargs.get("job_id")
        if not job_id:
            return "❌ 'job_id' is required for cancel action."

        if self._service.cancel_job(job_id):
            return f"✅ Cancelled job {job_id}"
        else:
            return f"❌ Job {job_id} not found or could not be cancelled."

    async def _run_now(self, kwargs: dict) -> str:
        job_id = kwargs.get("job_id")
        if not job_id:
            return "❌ 'job_id' is required for run_now action."

        return await self._service.run_job_now(job_id)

    def _health(self, kwargs: dict) -> str:
        status = self._service.health_check()
        icon = "✅" if status["status"] == "healthy" else "⚠️"

        lines = [f"{icon} **Scheduler Health: {status['status'].upper()}**"]
        lines.append(f"• Active Jobs: {status['jobs_count']}")
        lines.append(f"• Resource Guard: {status['resource_guard']}")
        lines.append(f"• DB Connected: {status['db_connected']}")

        return "\n".join(lines)
