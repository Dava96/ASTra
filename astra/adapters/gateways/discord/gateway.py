"""Discord gateway implementation with slash commands.

This is the core DiscordGateway class. Command registration and embed building
are delegated to submodules for better organization.
"""

import asyncio
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

        # Command handlers
        self._handlers: dict[str, Callable[[Command], Awaitable[None]]] = {}

        # Setup event handlers
        self._setup_events()

    def _setup_events(self) -> None:
        """Setup Discord event handlers."""
        @self._client.event
        async def on_ready():
            logger.info(f"Logged in as {self._client.user} (ID: {self._client.user.id})")
            await self._tree.sync()
            logger.info("Commands synced")

    def register_command(
        self,
        name: str,
        handler: Callable[[Command], Awaitable[None]],
        description: str = ""
    ) -> None:
        """Register a slash command."""
        self._handlers[name] = handler

        @self._tree.command(name=name, description=description)
        async def command_wrapper(interaction: discord.Interaction, request: str = ""):
            if not self.is_user_authorized(str(interaction.user.id)):
                await interaction.response.send_message(
                    "⛔ You are not authorized to use this bot.",
                    ephemeral=True
                )
                return

            cmd = Command(
                name=name,
                args={"request": request},
                user_id=str(interaction.user.id),
                channel_id=str(interaction.channel_id),
                raw_interaction=interaction
            )
            await interaction.response.defer()
            if name in self._handlers:
                await self._handlers[name](cmd)

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
        channel = self._client.get_channel(int(message.channel_id))
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

            if last_message and last_message.author == self._client.user and "█" in last_message.content:
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

    def _save_allowed_users(self) -> None:
        """Persist allowed users."""
        self._auth._save_allowed_users()

    async def send_followup(
        self,
        interaction_ref: discord.Interaction,
        content: str = "",
        file_path: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Send a followup message to an interaction."""
        embed = None
        file = None

        if file_path:
            file = discord.File(file_path, filename=os.path.basename(file_path))

        if metadata:
            # Handle screenshot/special formatting via metadata
            if "load_time_ms" in metadata:
                from datetime import UTC, datetime
                embed = discord.Embed(
                    title=f"📸 Screenshot: {metadata.get('title', 'Unknown')}",
                    url=metadata.get('url'),
                    color=discord.Color.blue(),
                    timestamp=datetime.now(UTC)
                )
                embed.add_field(name="Load Time", value=f"{metadata['load_time_ms']}ms")
                if file:
                    embed.set_image(url=f"attachment://{file.filename}")

        if len(content) > 1900 and not embed:
            from io import StringIO
            file = discord.File(StringIO(content), filename="details.txt")
            await interaction_ref.followup.send("📄 Full details attached:", file=file)
        else:
            await interaction_ref.followup.send(content, embed=embed, file=file)

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
        on_config: Callable[[Command], Awaitable[None]] = None
    ) -> None:
        """Register all built-in slash commands.

        This method registers the core task commands, config commands,
        auth commands, and utility commands.
        """
        # Import command registration from commands module
        from astra.adapters.gateways.discord.commands import register_all_commands
        register_all_commands(
            gateway=self,
            tree=self._tree,
            handlers=self._handlers,
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
            on_config=on_config
        )


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
