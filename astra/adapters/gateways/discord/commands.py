"""Discord slash command registration.

This module contains all the slash command definitions for the Discord gateway.
Commands are registered dynamically when register_all_commands is called.
"""

from collections.abc import Awaitable, Callable
from functools import wraps

import discord
from discord import app_commands

from astra.adapters.gateways.discord.embeds import build_config_embed, build_help_embed
from astra.interfaces.gateway import Command


# Define decorators for repetitive checks
def check_auth(func):
    """Decorator to check if user is authorized."""
    @wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        if not gateway_instance.is_user_authorized(str(interaction.user.id)):
            await interaction.response.send_message("⛔ Not authorized.", ephemeral=True)
            return
        await func(interaction, *args, **kwargs)
    return wrapper


def check_mfa(func):
    """Decorator to check for active MFA session."""
    @wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        if not gateway_instance._auth.has_active_session(str(interaction.user.id)):
            await interaction.response.send_message(
                "🔒 MFA session required. Use `/mfa login` to authenticate.",
                ephemeral=True
            )
            return
        await func(interaction, *args, **kwargs)
    return wrapper


def check_admin(func):
    """Decorator to check if user is admin AND has active MFA session."""
    @wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        user_id = str(interaction.user.id)
        if not gateway_instance.is_admin(user_id):
            await interaction.response.send_message("⛔ Admin only.", ephemeral=True)
            return

        if not gateway_instance._auth.has_active_session(user_id):
            await interaction.response.send_message(
                "🔒 Admin action requires MFA. Use `/mfa login` to authenticate.",
                ephemeral=True
            )
            return

        await func(interaction, *args, **kwargs)
    return wrapper

# Global variable to hold gateway reference for decorators
gateway_instance = None

def register_all_commands(
    gateway,
    tree: app_commands.CommandTree,
    handlers: dict,
    on_feature: Callable[[Command], Awaitable[None]],
    on_fix: Callable[[Command], Awaitable[None]],
    on_quick: Callable[[Command], Awaitable[None]],
    on_checkout: Callable[[Command], Awaitable[None]],
    on_status: Callable[[Command], Awaitable[None]],
    on_cancel: Callable[[Command], Awaitable[None]],
    on_last: Callable[[Command], Awaitable[None]],
    on_approve: Callable[[Command], Awaitable[None]] = None,
    on_revise: Callable[[Command], Awaitable[None]] = None,
    on_screenshot: Callable[[Command], Awaitable[None]] = None,
    on_history: Callable[[Command], Awaitable[None]] = None,
    on_docker: Callable[[Command], Awaitable[None]] = None,
    on_cron: Callable[[Command], Awaitable[None]] = None,
    on_web: Callable[[Command], Awaitable[None]] = None,
    on_cleanup: Callable[[Command], Awaitable[None]] = None,
    on_model: Callable[[Command], Awaitable[None]] = None,
    on_auth: Callable[[Command], Awaitable[None]] = None,
    on_health: Callable[[Command], Awaitable[None]] = None,
    on_tools: Callable[[Command], Awaitable[None]] = None,
    on_config: Callable[[Command], Awaitable[None]] = None
) -> None:
    """Register all built-in slash commands."""
    global gateway_instance
    gateway_instance = gateway

    # --- Task Commands ---

    @tree.command(name="feature", description="Request a new feature implementation")
    @check_auth
    async def feature_cmd(interaction: discord.Interaction, request: str):
        await interaction.response.defer()
        cmd = Command(
            name="feature", args={"request": request, "type": "feature"},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_feature(cmd)

    @tree.command(name="fix", description="Fix a bug or issue")
    @check_auth
    async def fix_cmd(interaction: discord.Interaction, description: str):
        await interaction.response.defer()
        cmd = Command(
            name="fix", args={"request": description, "type": "fix"},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_fix(cmd)

    @tree.command(name="quick", description="Quick single-file edit")
    @check_auth
    async def quick_cmd(interaction: discord.Interaction, file: str, change: str):
        await interaction.response.defer()
        cmd = Command(
            name="quick", args={"request": change, "file": file, "type": "quick"},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_quick(cmd)

    # --- Project Management Commands ---

    @tree.command(name="checkout", description="Set active project repository")
    @check_auth
    async def checkout_cmd(interaction: discord.Interaction, repo: str):
        await interaction.response.defer()
        cmd = Command(
            name="checkout", args={"repo": repo},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_checkout(cmd)

    @tree.command(name="status", description="Check queue and task status")
    @check_auth
    async def status_cmd(interaction: discord.Interaction):
        await interaction.response.defer()
        cmd = Command(
            name="status", args={},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_status(cmd)

    @tree.command(name="cancel", description="Cancel current task")
    @check_auth
    async def cancel_cmd(interaction: discord.Interaction):
        await interaction.response.defer()
        cmd = Command(
            name="cancel", args={},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_cancel(cmd)

    @tree.command(name="last", description="Show last task result")
    @check_auth
    async def last_cmd(interaction: discord.Interaction):
        await interaction.response.defer()
        cmd = Command(
            name="last", args={},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_last(cmd)

    @tree.command(name="history", description="View recent task history")
    @check_auth
    async def history_cmd(interaction: discord.Interaction, limit: int = 5):
        await interaction.response.defer()
        cmd = Command(
            name="history", args={"limit": limit},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_history(cmd)

    # --- Interaction Commands (Approve/Revise/Screenshot) ---

    if on_approve:
        @tree.command(name="approve", description="Approve a pending plan")
        @check_auth
        async def approve_cmd(interaction: discord.Interaction, task_id: str):
            await interaction.response.defer()
            cmd = Command(
                name="approve", args={"task_id": task_id},
                user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
                raw_interaction=interaction
            )
            await on_approve(cmd)

    if on_revise:
        @tree.command(name="revise", description="Revise a plan with feedback")
        @check_auth
        async def revise_cmd(interaction: discord.Interaction, task_id: str, feedback: str):
            await interaction.response.defer()
            cmd = Command(
                name="revise", args={"task_id": task_id, "feedback": feedback},
                user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
                raw_interaction=interaction
            )
            await on_revise(cmd)

    if on_screenshot:
        @tree.command(name="screenshot", description="Capture a screenshot of a website")
        @app_commands.describe(url="The URL to capture", full_page="Capture full scrollable page")
        @check_auth
        async def screenshot_cmd(interaction: discord.Interaction, url: str, full_page: bool = False):
            await interaction.response.defer()
            cmd = Command(
                name="screenshot", args={"url": url, "full_page": full_page},
                user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
                raw_interaction=interaction
            )
            await on_screenshot(cmd)

    # --- Docker Commands ---

    @tree.command(name="docker", description="Check Docker container health")
    @check_mfa
    async def docker_cmd(interaction: discord.Interaction):
        await interaction.response.defer()
        cmd = Command(
            name="docker", args={},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_docker(cmd)

    # --- Cron Commands ---

    cron_group = app_commands.Group(name="cron", description="Manage automated cron jobs")

    @cron_group.command(name="list", description="List active cron jobs")
    @check_auth
    async def cron_list(interaction: discord.Interaction):
        await interaction.response.defer()
        cmd = Command(
            name="cron", args={"action": "list"},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_cron(cmd)

    @cron_group.command(name="schedule", description="Schedule a new cron job")
    @app_commands.describe(
        cron="Cron expression (e.g. '0 9 * * *')",
        command="Command to run",
        description="Optional description"
    )
    @check_admin # Restrict scheduling to admins for security
    async def cron_schedule(interaction: discord.Interaction, cron: str, command: str, description: str = ""):
        await interaction.response.defer()
        cmd = Command(
            name="cron", args={"action": "schedule", "cron": cron, "command": command, "description": description},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_cron(cmd)

    @cron_group.command(name="cancel", description="Cancel a cron job")
    @check_admin
    async def cron_cancel(interaction: discord.Interaction, job_id: str):
        await interaction.response.defer()
        cmd = Command(
            name="cron", args={"action": "cancel", "job_id": job_id},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_cron(cmd)

    @cron_group.command(name="run", description="Run a cron job immediately")
    @check_auth
    async def cron_run(interaction: discord.Interaction, job_id: str):
        await interaction.response.defer()
        cmd = Command(
            name="cron", args={"action": "run_now", "job_id": job_id},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_cron(cmd)

    @cron_group.command(name="health", description="Check scheduler health")
    @check_auth
    async def cron_health(interaction: discord.Interaction):
        await interaction.response.defer()
        cmd = Command(
            name="cron", args={"action": "health"},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_cron(cmd)

    tree.add_command(cron_group)

    # --- Web Search Command ---

    @tree.command(name="web", description="Search the web")
    @check_mfa
    async def web_cmd(interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        cmd = Command(
            name="web", args={"query": query},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_web(cmd)

    # --- Auth Administration ---

    auth_group = app_commands.Group(name="auth", description="Manage authorized users (admin only)")

    @auth_group.command(name="add", description="Add an authorized user")
    @check_admin
    async def auth_add(interaction: discord.Interaction, user: discord.User):
        if gateway.add_authorized_user(str(user.id)):
            await interaction.response.send_message(f"✅ Added {user.mention} to authorized users.")
        else:
            await interaction.response.send_message(f"ℹ️ {user.mention} is already authorized.")

    @auth_group.command(name="remove", description="Remove an authorized user")
    @check_admin
    async def auth_remove(interaction: discord.Interaction, user: discord.User):
        if gateway.remove_authorized_user(str(user.id)):
            await interaction.response.send_message(f"✅ Removed {user.mention} from authorized users.")
        else:
            await interaction.response.send_message(f"ℹ️ {user.mention} was not in the list.")

    @auth_group.command(name="list", description="List all authorized users")
    @check_admin
    async def auth_list(interaction: discord.Interaction):
        users = gateway._auth.get_authorized_users()
        if users:
            user_list = "\n".join([f"• <@{uid}>" for uid in users])
            await interaction.response.send_message(f"**Authorized Users:**\n{user_list}")
        else:
            await interaction.response.send_message("No authorized users configured.")

    tree.add_command(auth_group)

    # --- MFA Management ---

    mfa_group = app_commands.Group(name="mfa", description="Manage Multi-Factor Authentication")

    @mfa_group.command(name="setup", description="Get your MFA setup secret")
    @check_auth
    async def mfa_setup(interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        secret = gateway._auth.get_mfa_secret(user_id)

        # Build otpauth URI for QR codes
        import pyotp
        uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=interaction.user.name,
            issuer_name="ASTra"
        )

        instructions = (
            "🔐 **MFA Setup**\n\n"
            f"1. Copy this secret: `{secret}`\n"
            "2. Or use this URI in your authenticator app:\n"
            f"<{uri}>\n\n"
            "**⚠️ Keep this secret private!**"
        )
        await interaction.response.send_message(instructions, ephemeral=True)

    @mfa_group.command(name="login", description="Start an authenticated MFA session")
    @app_commands.describe(code="6-digit code from your authenticator app")
    @check_auth
    async def mfa_login(interaction: discord.Interaction, code: str):
        if gateway._auth.verify_mfa(str(interaction.user.id), code):
            await interaction.response.send_message(
                "✅ MFA authentication successful. Session started for 30 days.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Invalid MFA code. Please try again.",
                ephemeral=True
            )

    @mfa_group.command(name="status", description="Check your MFA session status")
    @check_auth
    async def mfa_status(interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if gateway._auth.has_active_session(user_id):
            # Calculate remaining time
            import time
            expiry = gateway._auth._sessions.get(user_id, 0)
            remaining = int((expiry - time.time()) / 60)
            await interaction.response.send_message(
                f"✅ You have an active MFA session. ({remaining} minutes remaining)",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "🔒 No active MFA session. Use `/mfa login` to authenticate.",
                ephemeral=True
            )

    @mfa_group.command(name="reset", description="Reset your MFA secret (admin only)")
    @app_commands.describe(user="The user whose MFA should be reset")
    @check_admin
    async def mfa_reset(interaction: discord.Interaction, user: discord.User):
        gateway._auth.reset_mfa(str(user.id))
        await interaction.response.send_message(
            f"✅ MFA secret for {user.mention} has been reset.",
            ephemeral=True
        )

    tree.add_command(mfa_group)

    # --- System Config & Help ---

    @tree.command(name="help", description="Show all available commands")
    async def help_cmd(interaction: discord.Interaction):
        embed = build_help_embed()
        await interaction.response.send_message(embed=embed)

    config_group = app_commands.Group(name="config", description="View and manage configuration")

    @config_group.command(name="list", description="List all configuration options")
    @check_auth
    async def config_list(interaction: discord.Interaction):
        embed = build_config_embed(gateway._config)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="get", description="Get a specific config value")
    @check_auth
    async def config_get(interaction: discord.Interaction, key: str):
        parts = key.split(".")
        value = gateway._config
        try:
            for part in parts:
                value = getattr(value, part)
            await interaction.response.send_message(f"**{key}:** `{value}`", ephemeral=True)
        except (AttributeError, TypeError):
            await interaction.response.send_message(f"❌ Config key `{key}` not found.", ephemeral=True)

    tree.add_command(config_group)

    # --- Model Management ---

    model_group = app_commands.Group(name="model", description="Manage LLM models")

    @model_group.command(name="current", description="Show current model configuration")
    @check_auth
    async def model_current(interaction: discord.Interaction):
        planning = gateway._config.llm.planning_model or "not set"
        coding = gateway._config.llm.coding_model or "same as planning"
        await interaction.response.send_message(
            f"**Current Models:**\n🧠 Planning: `{planning}`\n💻 Coding: `{coding}`"
        )

    @model_group.command(name="set", description="Set the active model (admin only)")
    @check_admin
    async def model_set(interaction: discord.Interaction, model: str, target: str = "planning"):
        await interaction.response.defer()
        cmd = Command(
            name="model", args={"model": model, "target": target},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_model(cmd)

    tree.add_command(model_group)

    # --- Cleanup ---

    @tree.command(name="cleanup", description="Remove stale data to free disk space")
    @app_commands.describe(max_age_days="Delete collections not accessed in this many days (default: 30)")
    @check_admin
    async def cleanup_cmd(interaction: discord.Interaction, max_age_days: int = 30):
        await interaction.response.defer()
        cmd = Command(
            name="cleanup", args={"max_age_days": max_age_days},
            user_id=str(interaction.user.id), channel_id=str(interaction.channel_id),
            raw_interaction=interaction
        )
        await on_cleanup(cmd)
