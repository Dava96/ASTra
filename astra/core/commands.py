"""Central command registration for all gateways.

This module defines the standard set of commands available across all ASTra gateways
(Discord, Console, Web, etc.). It uses the unified Gateway interface to register commands with
strict parameter schemas and security requirements.
"""

from collections.abc import Awaitable, Callable

from astra.interfaces.gateway import Command, CommandParam, Gateway


def register_all_commands(
    gateway: Gateway,
    on_feature: Callable[[Command], Awaitable[None]],
    on_fix: Callable[[Command], Awaitable[None]],
    on_quick: Callable[[Command], Awaitable[None]],
    on_checkout: Callable[[Command], Awaitable[None]],
    on_status: Callable[[Command], Awaitable[None]],
    on_cancel: Callable[[Command], Awaitable[None]],
    on_last: Callable[[Command], Awaitable[None]],
    on_approve: Callable[[Command], Awaitable[None]] | None = None,
    on_revise: Callable[[Command], Awaitable[None]] | None = None,
    on_screenshot: Callable[[Command], Awaitable[None]] | None = None,
    on_history: Callable[[Command], Awaitable[None]] | None = None,
    on_docker: Callable[[Command], Awaitable[None]] | None = None,
    on_cron: Callable[[Command], Awaitable[None]] | None = None,
    on_web: Callable[[Command], Awaitable[None]] | None = None,
    on_cleanup: Callable[[Command], Awaitable[None]] | None = None,
    on_model: Callable[[Command], Awaitable[None]] | None = None,
    on_auth: Callable[[Command], Awaitable[None]] | None = None,
    on_health: Callable[[Command], Awaitable[None]] | None = None,
    on_tools: Callable[[Command], Awaitable[None]] | None = None,
    on_config: Callable[[Command], Awaitable[None]] | None = None,
) -> None:
    """Register all built-in commands with the gateway."""

    # --- Core Task Commands ---

    gateway.register_command(
        name="feature",
        description="Request a new feature implementation",
        handler=on_feature,
        params=[
            CommandParam(name="request", description="Feature description", type=str),
        ],
        requires_auth=True,
    )

    gateway.register_command(
        name="fix",
        description="Fix a bug or issue",
        handler=on_fix,
        params=[
            CommandParam(name="description", description="Issue description", type=str),
        ],
        requires_auth=True,
    )

    gateway.register_command(
        name="quick",
        description="Quick single-file edit",
        handler=on_quick,
        params=[
            CommandParam(
                name="file", description="Target file (relative path)", type=str
            ),
            CommandParam(name="change", description="Description of changes", type=str),
        ],
        requires_auth=True,
    )

    # --- Project Management Commands ---

    gateway.register_command(
        name="checkout",
        description="Set active project repository",
        handler=on_checkout,
        params=[
            CommandParam(name="repo", description="Repository path or URL", type=str),
        ],
        requires_auth=True,
    )

    gateway.register_command(
        name="status",
        description="Check queue and task status",
        handler=on_status,
        requires_auth=True,
    )

    gateway.register_command(
        name="cancel",
        description="Cancel current task",
        handler=on_cancel,
        requires_auth=True,
    )

    gateway.register_command(
        name="last",
        description="Show last task result",
        handler=on_last,
        requires_auth=True,
    )

    if on_history:
        gateway.register_command(
            name="history",
            description="View recent task history",
            handler=on_history,
            params=[
                CommandParam(
                    name="limit",
                    description="Number of tasks to show",
                    type=int,
                    default=5,
                    required=False,
                ),
            ],
            requires_auth=True,
        )

    # --- Interaction Commands ---

    if on_approve:
        gateway.register_command(
            name="approve",
            description="Approve a pending plan",
            handler=on_approve,
            params=[
                CommandParam(name="task_id", description="Task ID to approve", type=str),
            ],
            requires_auth=True,
        )

    if on_revise:
        gateway.register_command(
            name="revise",
            description="Revise a plan with feedback",
            handler=on_revise,
            params=[
                CommandParam(name="task_id", description="Task ID to revise", type=str),
                CommandParam(
                    name="feedback", description="Feedback for revision", type=str
                ),
            ],
            requires_auth=True,
        )

    if on_screenshot:
        gateway.register_command(
            name="screenshot",
            description="Capture a screenshot of a website",
            handler=on_screenshot,
            params=[
                CommandParam(name="url", description="The URL to capture", type=str),
                CommandParam(
                    name="full_page",
                    description="Capture full scrollable page",
                    type=bool,
                    default=False,
                    required=False,
                ),
            ],
            requires_auth=True,
        )

    # --- Docker Commands ---

    if on_docker:
        gateway.register_command(
            name="docker",
            description="Check Docker container health",
            handler=on_docker,
            requires_mfa=True,
        )

    # --- Cron Commands ---

    if on_cron:
        gateway.register_command_group(
            name="cron", description="Manage automated cron jobs"
        )

        gateway.register_command(
            name="list",
            group="cron",
            description="List active cron jobs",
            handler=lambda cmd: _wrapper_with_arg(on_cron, cmd, action="list"),
            requires_auth=True,
        )

        gateway.register_command(
            name="schedule",
            group="cron",
            description="Schedule a new cron job",
            handler=lambda cmd: _wrapper_with_arg(on_cron, cmd, action="schedule"),
            params=[
                CommandParam(
                    name="cron",
                    description="Cron expression (e.g. '0 9 * * *')",
                    type=str,
                ),
                CommandParam(name="command", description="Command to run", type=str),
                CommandParam(
                    name="description", description="Optional description", type=str, required=False, default=""
                ),
            ],
            requires_admin=True,
        )

        gateway.register_command(
            name="cancel",
            group="cron",
            description="Cancel a cron job",
            handler=lambda cmd: _wrapper_with_arg(on_cron, cmd, action="cancel"),
            params=[
                CommandParam(name="job_id", description="Job ID to cancel", type=str),
            ],
            requires_admin=True,
        )

        gateway.register_command(
            name="run",
            group="cron",
            description="Run a cron job immediately",
            handler=lambda cmd: _wrapper_with_arg(on_cron, cmd, action="run_now"),
            params=[
                CommandParam(name="job_id", description="Job ID to run", type=str),
            ],
            requires_auth=True,
        )

        gateway.register_command(
            name="health",
            group="cron",
            description="Check scheduler health",
            handler=lambda cmd: _wrapper_with_arg(on_cron, cmd, action="health"),
            requires_auth=True,
        )

    # --- Web Search ---

    if on_web:
        gateway.register_command(
            name="web",
            description="Search the web",
            handler=on_web,
            params=[
                CommandParam(name="query", description="Search query", type=str),
            ],
            requires_mfa=True,
        )

    # --- Auth Administration ---

    if on_auth:
        gateway.register_command_group(
            name="auth", description="Manage authorized users (admin only)"
        )

        gateway.register_command(
            name="add",
            group="auth",
            description="Add an authorized user",
            handler=on_auth,
            params=[
                CommandParam(
                    name="user", description="User ID or mention", type=str
                ),
            ],
            requires_admin=True,
        )

        gateway.register_command(
            name="remove",
            group="auth",
            description="Remove an authorized user",
            handler=on_auth,
            params=[
                CommandParam(name="user", description="User ID or mention", type=str),
            ],
            requires_admin=True,
        )

        gateway.register_command(
            name="list",
            group="auth",
            description="List all authorized users",
            handler=on_auth,
            requires_admin=True,
        )

    # --- Config Commands ---

    if on_config:
        gateway.register_command_group(name="config", description="View and manage configuration")

        gateway.register_command(
            name="list",
            group="config",
            description="View current configuration",
            handler=lambda cmd: _wrapper_with_arg(on_config, cmd, action="list"),
            requires_auth=True,
        )

        gateway.register_command(
            name="set",
            group="config",
            description="Set a config value",
            handler=lambda cmd: _wrapper_with_arg(on_config, cmd, action="set"),
            params=[
                CommandParam(name="key", description="Config key (e.g. llm.model)", type=str),
                CommandParam(name="value", description="New value", type=str),
            ],
            requires_admin=True,
        )

        gateway.register_command(
            name="get",
            group="config",
            description="Get a specific config value",
            handler=lambda cmd: _wrapper_with_arg(on_config, cmd, action="get"),
            params=[
                CommandParam(name="key", description="Config key (e.g. llm.model)", type=str),
            ],
            requires_auth=True,
        )

    # --- Model Commands ---

    if on_model:
        gateway.register_command_group(name="model", description="Manage LLM models")

        gateway.register_command(
            name="current",
            group="model",
            description="Show current model configuration",
            handler=lambda cmd: _wrapper_with_arg(on_model, cmd, action="current"),
            requires_auth=True,
        )

        gateway.register_command(
            name="set",
            group="model",
            description="Set the active model",
            handler=lambda cmd: _wrapper_with_arg(on_model, cmd, action="set"),
            params=[
                CommandParam(name="model", description="Model ID", type=str),
                CommandParam(
                    name="target",
                    description="Target (planning/coding)",
                    type=str,
                    default="planning",
                    required=False,
                ),
            ],
            requires_admin=True,
        )

    # --- Cleanup ---

    if on_cleanup:
        gateway.register_command(
            name="cleanup",
            description="Remove stale data",
            handler=on_cleanup,
            params=[
                CommandParam(
                    name="max_age_days",
                    description="Delete days older than",
                    type=int,
                    default=30,
                    required=False
                ),
            ],
            requires_admin=True,
        )


async def _wrapper_with_arg(handler, cmd: Command, **kwargs):
    """Helper to inject hardcoded args into command for handler compatibility."""
    # Merge kwargs into cmd.args
    cmd.args.update(kwargs)
    await handler(cmd)
