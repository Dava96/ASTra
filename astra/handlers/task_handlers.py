"""Handlers for task-related commands."""

import logging

from astra.config import Config
from astra.core.orchestrator import Orchestrator
from astra.core.task_queue import TaskQueue
from astra.interfaces.gateway import Command, Gateway

logger = logging.getLogger(__name__)


class TaskHandlers:
    """Handles execution of task-related slash commands."""

    def __init__(
        self, gateway: Gateway, orchestrator: Orchestrator, queue: TaskQueue, config: Config
    ):
        self.gateway = gateway
        self.orchestrator = orchestrator
        self.queue = queue
        self.config = config

    async def handle_feature(self, cmd: Command):
        """Handle /feature command."""
        request = cmd.args.get("request", "")
        if not request:
            await self.gateway.send_followup(
                cmd.raw_interaction, "❌ Please provide a feature description"
            )
            return

        project = self.orchestrator.get_active_project()
        if not project:
            await self.gateway.send_followup(
                cmd.raw_interaction, "❌ No active project. Please use `/checkout` first."
            )
            return

        task = self.queue.add(
            task_type="feature",
            request=request,
            user_id=cmd.user_id,
            channel_id=cmd.channel_id,
            project=project,
        )

        position = self.queue.get_position(task.id)
        await self.gateway.send_followup(
            cmd.raw_interaction,
            f"📥 Task queued (ID: `{task.id}`, Position: {position})\nRequest: {request[:100]}",
        )

    async def handle_fix(self, cmd: Command):
        """Handle /fix command - similar to feature but for bugs."""
        request = cmd.args.get("request", "")
        if not request:
            await self.gateway.send_followup(
                cmd.raw_interaction, "❌ Please provide a bug description"
            )
            return

        project = self.orchestrator.get_active_project()
        if not project:
            await self.gateway.send_followup(
                cmd.raw_interaction, "❌ No active project. Please use `/checkout` first."
            )
            return

        task = self.queue.add(
            task_type="fix",
            request=f"[BUG FIX] {request}",
            user_id=cmd.user_id,
            channel_id=cmd.channel_id,
            project=project,
        )
        position = self.queue.get_position(task.id)
        await self.gateway.send_followup(
            cmd.raw_interaction, f"🐛 Bug fix queued (ID: `{task.id}`, Position: {position})"
        )

    async def handle_quick(self, cmd: Command):
        """Handle /quick command - fast single-file edit."""
        file_path = cmd.args.get("file", "")
        change = cmd.args.get("change", "")

        if not file_path or not change:
            await self.gateway.send_followup(
                cmd.raw_interaction, "❌ Usage: /quick <file> <change>"
            )
            return

        project = self.orchestrator.get_active_project()
        task = self.queue.add(
            task_type="quick",
            request=f"[QUICK EDIT] File: {file_path} | Change: {change}",
            user_id=cmd.user_id,
            channel_id=cmd.channel_id,
            project=project,
        )
        await self.gateway.send_followup(
            cmd.raw_interaction, f"⚡ Quick edit queued (ID: `{task.id}`)"
        )

    async def handle_status(self, cmd: Command):
        """Handle /status command."""
        status = self.queue.get_queue_status()

        msg = "📊 **ASTra Status**\n\n"
        msg += f"**Active Project**: {self.orchestrator.get_active_project() or 'None'}\n"
        msg += f"**Queue**: {status['queued']} tasks\n"

        if status["current"]:
            msg += f"**Current Task**: {status['current']['request'][:50]}...\n"

        if status["recent"]:
            msg += "\n**Recent Tasks**:\n"
            for t in status["recent"][-3:]:
                emoji = "✅" if t["status"] == "success" else "❌"
                msg += f"  {emoji} `{t['id']}`: {t['request'][:30]}...\n"

        await self.gateway.send_followup(cmd.raw_interaction, msg)

    async def handle_cancel(self, cmd: Command):
        """Handle /cancel command."""
        if self.queue.cancel_current():
            await self.gateway.send_followup(cmd.raw_interaction, "🛑 Cancellation requested")
        else:
            await self.gateway.send_followup(cmd.raw_interaction, "ℹ️ No task currently running")

    async def handle_last(self, cmd: Command):
        """Handle /last command."""
        last = self.queue.get_last_result(cmd.user_id)
        if last:
            status = "✅ Success" if last.status.value == "success" else "❌ Failed"
            msg = f"**Last Task** ({status})\n\n"
            msg += f"Request: {last.request}\n"
            if last.result and last.result.get("pr_url"):
                msg += f"PR: {last.result['pr_url']}\n"
            if last.error:
                msg += f"Error: {last.error}\n"
            await self.gateway.send_followup(cmd.raw_interaction, msg)
        else:
            await self.gateway.send_followup(cmd.raw_interaction, "ℹ️ No completed tasks found")

    async def handle_history(self, cmd: Command):
        """Handle /history command."""
        # Get full state
        current = self.queue.get_current()
        queued = self.queue._queued_list  # Direct access for listing
        history = self.queue.get_history(limit=10)

        msg = "📜 **Task History**\n\n"

        if current:
            msg += f"**▶️ Current**: `{current.id}` - {current.request[:50]}...\n\n"

        if queued:
            msg += "**⏳ Queued**:\n"
            for i, t in enumerate(queued[:5]):
                msg += f"{i + 1}. `{t.id}`: {t.request[:40]}...\n"
            if len(queued) > 5:
                msg += f"... and {len(queued) - 5} more\n"
            msg += "\n"

        if history:
            msg += "**✅ Recently Completed**:\n"
            for t in history:
                emoji = "✅" if t.status.value == "success" else "❌"
                # Handle Task status enum or value
                msg += f"{emoji} `{t.id}`: {t.request[:40]}...\n"
        else:
            msg += "(No completed tasks)"

        await self.gateway.send_followup(cmd.raw_interaction, msg)

    async def handle_approve(self, cmd: Command):
        """Handle /approve command."""
        task_id = cmd.args.get("task_id")
        try:
            await self.orchestrator.resume_task(task_id)
            await self.gateway.send_followup(
                cmd.raw_interaction, f"✅ Task `{task_id}` approved and queued for execution."
            )
        except Exception as e:
            await self.gateway.send_followup(cmd.raw_interaction, f"❌ Failed to approve task: {e}")

    async def handle_revise(self, cmd: Command):
        """Handle /revise command."""
        task_id = cmd.args.get("task_id")
        feedback = cmd.args.get("feedback")
        try:
            await self.orchestrator.revise_plan(task_id, feedback)
            await self.gateway.send_followup(
                cmd.raw_interaction, f"📝 Task `{task_id}` queued for revision."
            )
        except Exception as e:
            await self.gateway.send_followup(cmd.raw_interaction, f"❌ Failed to revise task: {e}")
