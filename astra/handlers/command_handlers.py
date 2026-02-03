"""Command handlers for Discord commands."""

import logging

from astra.config import Config
from astra.core.clock import Clock, SystemClock
from astra.core.orchestrator import Orchestrator
from astra.core.task_queue import TaskQueue
from astra.handlers.project_handlers import ProjectHandlers
from astra.handlers.system_handlers import SystemHandlers
from astra.handlers.task_handlers import TaskHandlers
from astra.interfaces.gateway import Command, Gateway

logger = logging.getLogger(__name__)

class CommandHandler:
    """Handles execution of slash commands by delegating to specialized handlers."""

    def __init__(self, gateway: Gateway, orchestrator: Orchestrator, queue: TaskQueue, config: Config, clock: Clock = None):
        self.gateway = gateway
        self.orchestrator = orchestrator
        self.queue = queue
        self.config = config
        self.clock = clock or SystemClock()

        # Initialize sub-handlers
        self.tasks = TaskHandlers(gateway, orchestrator, queue, config)
        self.projects = ProjectHandlers(gateway, orchestrator, config, clock)
        self.system = SystemHandlers(gateway, orchestrator, config)

    # Delegate methods to sub-handlers for backward compatibility where needed
    # or just expose the sub-handlers. For now, let's keep the signatures expected by main.py

    async def handle_checkout(self, cmd: Command):
        await self.projects.handle_checkout(cmd)

    async def handle_feature(self, cmd: Command):
        await self.tasks.handle_feature(cmd)

    async def handle_fix(self, cmd: Command):
        await self.tasks.handle_fix(cmd)

    async def handle_quick(self, cmd: Command):
        await self.tasks.handle_quick(cmd)

    async def handle_status(self, cmd: Command):
        await self.tasks.handle_status(cmd)

    async def handle_cancel(self, cmd: Command):
        await self.tasks.handle_cancel(cmd)

    async def handle_last(self, cmd: Command):
        await self.tasks.handle_last(cmd)

    async def handle_approve(self, cmd: Command):
        await self.tasks.handle_approve(cmd)

    async def handle_revise(self, cmd: Command):
        await self.tasks.handle_revise(cmd)

    async def handle_history(self, cmd: Command):
        await self.tasks.handle_history(cmd)

    async def handle_config(self, cmd: Command):
        await self.system.handle_config(cmd)

    async def handle_model(self, cmd: Command):
        await self.system.handle_model(cmd)

    async def handle_auth(self, cmd: Command):
        await self.system.handle_auth(cmd)

    async def handle_health(self, cmd: Command):
        await self.system.handle_health(cmd)

    async def handle_tools(self, cmd: Command):
        await self.system.handle_tools(cmd)

    async def handle_screenshot(self, cmd: Command):
        await self.system.handle_screenshot(cmd)

    async def handle_docker(self, cmd: Command):
        await self.system.handle_docker(cmd)

    async def handle_cron(self, cmd: Command):
        await self.system.handle_cron(cmd)

    async def handle_web(self, cmd: Command):
        await self.system.handle_web(cmd)

    async def handle_cleanup(self, cmd: Command):
        await self.system.handle_cleanup(cmd)

