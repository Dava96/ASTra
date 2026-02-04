"""Discord gateway implementation with slash commands.

This is the core DiscordGateway class. Command registration and embed building
are delegated to submodules for better organization.
"""

import asyncio
import contextlib
import io
import logging
import os
import signal
from collections.abc import Awaitable, Callable
from typing import Any

import discord
from discord import app_commands

from astra.adapters.gateways.discord.auth import AuthManager
from astra.config import Config, get_config
from astra.interfaces.gateway import Command, Gateway, Message

logger = logging.getLogger(__name__)


class DiscordGateway(Gateway):
    """Discord bot implementation of the Gateway interface.

    This gateway connects to Discord via bot token and registers slash commands
    for interacting with the ASTra orchestrator.
    """

    def register_command_group(self, name: str, description: str = "") -> None:
        """Register a command group."""
        # Check if group already exists in tree
        for cmd in self._tree.get_commands():
            if cmd.name == name and isinstance(cmd, app_commands.Group):
                return

        group = app_commands.Group(name=name, description=description)
        group = app_commands.Group(name=name, description=description)
        self._tree.add_command(group)

    def set_chat_handler(self, handler: Callable[[str, str, str], Awaitable[str]]) -> None:
        """Set the handler for direct chat messages."""
        self._chat_handler = handler

    def register_command(
        self,
        name: str,
        handler: Callable[[Command], Awaitable[None]],
        description: str = "",
        params: list[Any] | None = None,
        group: str | None = None,
        requires_auth: bool = False,
        requires_admin: bool = False,
        requires_mfa: bool = False,
    ) -> None:
        """Register a slash command dynamically."""
        register_key = f"{group}.{name}" if group else name
        self._handlers[register_key] = handler
        self._handlers_meta[register_key] = {
            "auth": requires_auth,
            "admin": requires_admin,
            "mfa": requires_mfa
        }

        # Prepare parameter definitions
        param_defs = []
        param_names = []
        descriptions = {}
        if params:
            for param in params:
                param_names.append(param.name)
                descriptions[param.name] = param.description or "No description"

            for param in params:
                py_type = param.type
                type_name = py_type.__name__
                if param.required is False:
                    type_name = f"{type_name} | None"
                    default_s = f" = {repr(param.default)}"
                else:
                    default_s = ""

                param_defs.append(f"{param.name}: {type_name}{default_s}")
                param_names.append(param.name)
                descriptions[param.name] = param.description

        # Construct dynamic function
        func_args_str = ", ".join(["interaction: discord.Interaction"] + param_defs)

        # We bake the register_key into the call to ensure correct dispatch
        func_code = f"""
async def {name}_callback({func_args_str}):
    kwargs = {{}}
    {'; '.join([f"kwargs['{p}'] = {p}" for p in param_names])}
    await _internal_handler(interaction, "{register_key}", **kwargs)
"""

        ctx = {
            "discord": discord,
            "str": str,
            "int": int,
            "bool": bool,
            "_internal_handler": self._handle_dynamic_command,
        }

        exec(func_code, ctx)
        callback = ctx[f"{name}_callback"]

        # Apply descriptions
        if descriptions:
            describe_decorator = app_commands.describe(**descriptions)
            callback = describe_decorator(callback)

        # Create Command
        command_obj = app_commands.Command(
            name=name,
            description=description,
            callback=callback,
        )

        # Register
        if group:
            target_group = None
            for cmd in self._tree.get_commands():
                if cmd.name == group and isinstance(cmd, app_commands.Group):
                    target_group = cmd
                    break

            if target_group:
                target_group.add_command(command_obj)
            else:
                logger.error(f"Group {group} not found for command {name}")
        else:
            self._tree.add_command(command_obj)

    async def _handle_dynamic_command(self, interaction: discord.Interaction, register_key: str, **kwargs):
        """Internal handler for all dynamic commands."""
        # Check permissions
        meta = self._handlers_meta.get(register_key, {})
        user_id = str(interaction.user.id)

        if (meta.get("auth") or meta.get("admin") or meta.get("mfa")) and not self.is_user_authorized(
            user_id
        ):
            await interaction.response.send_message(
                "⛔ You are not authorized to use this bot.", ephemeral=True
            )
            return

        if meta.get("admin") and not self.is_admin(user_id):
            await interaction.response.send_message("⛔ Admin only.", ephemeral=True)
            return

        if meta.get("mfa") and not self._auth.has_active_session(user_id):
            await interaction.response.send_message(
                "🔒 MFA session required. Use `/mfa login` to authenticate.", ephemeral=True
            )
            return

        # Execute
        cmd = Command(
            name=interaction.command.name, # Use actual interaction name or register_key?
            # interaction.command.name is just the leaf name.
            # We pass args
            args=kwargs,
            user_id=user_id,
            channel_id=str(interaction.channel_id),
            raw_interaction=interaction,
        )

        await interaction.response.defer()
        if register_key in self._handlers:
            await self._handlers[register_key](cmd)


    def __init__(self, config: Config | None = None):
        self._config = config or get_config()
        self._token = os.getenv("DISCORD_TOKEN")

        # Setup intents
        intents = discord.Intents.default()
        intents.message_content = True

        # Create client
        self._client = discord.Client(intents=intents)
        self._tree = app_commands.CommandTree(self._client)

        # Authorization manager
        self._auth = AuthManager(self._config)

        # Command handlers and metadata
        self._handlers: dict[str, Callable[[Command], Awaitable[None]]] = {}
        self._handlers_meta: dict[str, dict[str, bool]] = {}

        # Setup event handlers
        self._setup_events()

    def _setup_events(self) -> None:
        """Setup Discord event handlers."""

        @self._client.event
        async def on_ready():
            logger.info(f"Logged in as {self._client.user} (ID: {self._client.user.id})")
            await self._tree.sync()
            logger.info("Commands synced")

        @self._client.event
        async def on_message(message: discord.Message):
            # Ignore own messages
            if message.author == self._client.user:
                return

            # Check if DM or Mention
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mention = (
                self._client.user
                and any(user.id == self._client.user.id for user in message.mentions)
            )

            if (is_dm or is_mention) and (hasattr(self, "_chat_handler") and self._chat_handler):
                async with message.channel.typing():
                    # Clean prompt
                    prompt = message.content
                    if is_mention:
                        prompt = prompt.replace(f"<@{self._client.user.id}>", "").strip()
                        prompt = prompt.replace(f"<@!{self._client.user.id}>", "").strip()

                    # Pass prompt, user_id, channel_id
                    response = await self._chat_handler(prompt, str(message.author.id), str(message.channel.id))

                    if response:
                        await message.reply(response)



    def register_built_in_commands(
        self,
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
        on_config: Callable[[Command], Awaitable[None]] = None,
    ) -> None:
        """Register all built-in slash commands using the core registry."""
        from astra.core.commands import register_all_commands

        register_all_commands(
            gateway=self,
            on_feature=on_feature,
            on_fix=on_fix,
            on_quick=on_quick,
            on_checkout=on_checkout,
            on_status=on_status,
            on_cancel=on_cancel,
            on_last=on_last,
            on_approve=on_approve,
            on_revise=on_revise,
            on_screenshot=on_screenshot,
            on_history=on_history,
            on_docker=on_docker,
            on_cron=on_cron,
            on_web=on_web,
            on_cleanup=on_cleanup,
            on_model=on_model,
            on_auth=on_auth,
            on_health=on_health,
            on_tools=on_tools,
            on_config=on_config,
        )

        # Register MFA commands locally
        self._register_mfa_commands()

    def _register_mfa_commands(self) -> None:
        """Register Discord-specific MFA management commands."""
        # MFA Group is created by core if we want, but register_all_commands doesn't do MFA commands yet.
        # We need to manually register the MFA group if it wasn't already.
        # Actually register_all_commands created "mfa" group?
        # Wait, I removed MFA from create_all_commands.

        self.register_command_group("mfa", "Manage Multi-Factor Authentication")

        # We can't use self.register_command easily because we need custom handlers
        # that interact with self._auth directly and return ephemeral messages differently?
        # Actually register_command matches the pattern.
        # We just need to define the handlers here.

        import pyotp

        from astra.interfaces.gateway import CommandParam

        async def mfa_setup(cmd: Command):
            user_id = cmd.user_id
            secret = self._auth.get_mfa_secret(user_id)
            uri = pyotp.totp.TOTP(secret).provisioning_uri(
                name=cmd.raw_interaction.user.name, issuer_name="ASTra"
            )
            msg = (
                "🔐 **MFA Setup**\n\n"
                f"1. Copy this secret: `{secret}`\n"
                "2. Or use this URI in your authenticator app:\n"
                f"<{uri}>\n\n"
                "**⚠️ Keep this secret private!**"
            )
            try:
                await cmd.raw_interaction.user.send(msg)
                await cmd.raw_interaction.followup.send("✅ Sent you a DM with the setup instructions!", ephemeral=True)
            except discord.Forbidden:
                await cmd.raw_interaction.followup.send("❌ I couldn't DM you. Please enable DMs from server members.", ephemeral=True)

        self.register_command(
            name="setup",
            group="mfa",
            description="Get your MFA setup secret",
            handler=mfa_setup,
            requires_auth=True
        )

        async def mfa_login(cmd: Command):
            code = cmd.args.get("code")
            if self._auth.verify_mfa(cmd.user_id, code):
                 await cmd.raw_interaction.followup.send(
                    "✅ MFA authentication successful. Session started for 30 days.", ephemeral=True
                )
            else:
                 await cmd.raw_interaction.followup.send(
                    "❌ Invalid MFA code. Please try again.", ephemeral=True
                )

        self.register_command(
            name="login",
            group="mfa",
            description="Start an authenticated MFA session",
            handler=mfa_login,
            params=[CommandParam("code", "6-digit code", str)],
            requires_auth=True
        )

        async def mfa_status(cmd: Command):
            if self._auth.has_active_session(cmd.user_id):
                expiry = int(self._auth._sessions.get(cmd.user_id, 0))

                # Discord timestamp formatting: <t:TIMESTAMP:STYLE>
                # f = short date time (e.g., June 18, 2021 12:42 PM)
                # R = relative time (e.g., in 20 minutes)
                await cmd.raw_interaction.followup.send(
                    f"✅ You have an **active** MFA session.\n"
                    f"Expires: <t:{expiry}:f> (<t:{expiry}:R>)",
                    ephemeral=True,
                )
            else:
                await cmd.raw_interaction.followup.send(
                    "🔒 No active MFA session. Use `/mfa login` to authenticate.", ephemeral=True
                )

        self.register_command(
            name="status",
            group="mfa",
            description="Check your MFA session status",
            handler=mfa_status,
            requires_auth=True
        )
    async def start(self) -> None:
        """Start the Discord bot."""
        if not self._token:
            logger.error("DISCORD_TOKEN environment variable not set")
            raise ValueError("DISCORD_TOKEN not set")

        loop = asyncio.get_event_loop()

        def handle_shutdown():
            logger.info("Shutdown signal received")
            asyncio.create_task(self.stop())

        try:
            loop.add_signal_handler(signal.SIGTERM, handle_shutdown)
            loop.add_signal_handler(signal.SIGINT, handle_shutdown)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

        await self._client.start(self._token)

    async def stop(self) -> None:
        """Gracefully stop the bot."""
        logger.info("Stopping Discord gateway...")
        await self._client.close()

    async def send_message(self, message: Message) -> None:
        """Send a message to a channel."""
        try:
            channel = self._client.get_channel(int(message.channel_id))
            if not channel:
                # Fallback to fetch (API call) if not in cache
                with contextlib.suppress(Exception):
                    channel = await self._client.fetch_channel(int(message.channel_id))

            if not channel:
                logger.error(f"Channel {message.channel_id} not found")
                return

            content = message.content

            if len(content) > 1900:
                file = discord.File(io.StringIO(content), filename="details.txt")
                await channel.send("📄 Full details attached:", file=file)
            else:
                if message.file_path:
                    file = discord.File(message.file_path)
                    await channel.send(content, file=file)
                else:
                    await channel.send(content)

        except Exception as e:
            logger.error(f"Failed to send message to {message.channel_id}: {e}")

    async def send_progress(self, channel_id: str, percent: int, description: str) -> None:
        """Send a progress update, editing the last message if it was a progress bar."""
        channel = self._client.get_channel(int(channel_id))
        if not channel:
            return

        filled = int(percent / 5)
        empty = 20 - filled
        bar = "█" * filled + "░" * empty
        content = f"{bar} {percent}% - {description}"

        # Check if we have a tracked progress message for this channel
        # For simplicity in this non-persistent gateway, we can try to find the last message
        # sent by us that looks like a progress bar, or just send new for now if tracking is complex.

        # NOTE: To truly edit, we need to track message IDs.
        # Since this is a simple refactor, let's use a simple heuristic:
        # If the last message in history is ours and contains "█", edit it.
        try:
            last_message = None
            async for msg in channel.history(limit=1):
                last_message = msg
                break

            if (
                last_message
                and last_message.author == self._client.user
                and "█" in last_message.content
            ):
                await last_message.edit(content=content)
            else:
                await channel.send(content)
        except Exception:
            # Fallback to sending new if history/edit fails
            await channel.send(content)

    async def request_confirmation(self, channel_id: str, prompt: str) -> bool:
        """Request user confirmation via UI Buttons."""
        channel = self._client.get_channel(int(channel_id))
        if not channel:
            return False

        view = ConfirmationView()
        await channel.send(prompt, view=view)

        await view.wait()
        return view.value is True

    # Auth delegation methods
    def is_user_authorized(self, user_id: str) -> bool:
        """Check if a user is authorized."""
        return self._auth.is_user_authorized(user_id)

    def is_admin(self, user_id: str) -> bool:
        """Check if a user is an admin."""
        return self._auth.is_admin(user_id)

    def add_authorized_user(self, user_id: str) -> bool:
        """Add an authorized user."""
        return self._auth.add_authorized_user(user_id)

    def remove_authorized_user(self, user_id: str) -> bool:
        """Remove an authorized user."""
        return self._auth.remove_authorized_user(user_id)

    async def broadcast(self, message: str) -> None:
        """Broadcast a message to all connected guilds."""
        for guild in self._client.guilds:
            channel = guild.system_channel
            if not channel:
                # Fallback to first text channel we can send to
                for c in guild.text_channels:
                    if c.permissions_for(guild.me).send_messages:
                        channel = c
                        break

            if channel:
                try:
                    await channel.send(message)
                except Exception as e:
                    logger.warning(f"Failed to broadcast to guild {guild.name}: {e}")

    def _save_allowed_users(self) -> None:
        """Persist allowed users."""
        self._auth._save_allowed_users()

    async def send_followup(
        self,
        interaction_ref: discord.Interaction,
        content: str = "",
        file_path: str | None = None,
        metadata: dict[str, Any] | None = None,
        ephemeral: bool = False,
    ) -> None:
        """Send a followup message to an interaction."""
        embed = None
        file = None

        if file_path:
            file = discord.File(file_path, filename=os.path.basename(file_path))

        if metadata and "load_time_ms" in metadata:
            # Handle screenshot/special formatting via metadata
            from datetime import UTC, datetime

            embed = discord.Embed(
                title=f"📸 Screenshot: {metadata.get('title', 'Unknown')}",
                url=metadata.get("url"),
                color=discord.Color.blue(),
                timestamp=datetime.now(UTC),
            )
            embed.add_field(name="Load Time", value=f"{metadata['load_time_ms']}ms")
            if file:
                embed.set_image(url=f"attachment://{file.filename}")

        if len(content) > 1900 and not embed:
            from io import StringIO

            file = discord.File(StringIO(content), filename="details.txt")
            await interaction_ref.followup.send("📄 Full details attached:", file=file, ephemeral=ephemeral)
        else:
            kwargs = {"content": content, "embed": embed, "ephemeral": ephemeral}
            if file:
                kwargs["file"] = file
            await interaction_ref.followup.send(**kwargs)



class ConfirmationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        # Disable buttons after click
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("✅ Confirmed!", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("❌ Cancelled.", ephemeral=True)


def create_discord_bot() -> DiscordGateway:
    """Factory function to create a configured Discord gateway."""
    return DiscordGateway()
