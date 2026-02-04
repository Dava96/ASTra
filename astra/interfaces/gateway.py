"""Abstract base class for messaging gateways (Discord, WhatsApp, etc.)."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class Command:
    """Represents an incoming command from a user."""

    name: str
    args: dict[str, Any]
    user_id: str
    channel_id: str
    raw_interaction: Any  # Platform-specific interaction object


@dataclass
class Message:
    """Represents a message to send to a user."""

    content: str
    channel_id: str
    ephemeral: bool = False
    file_path: str | None = None  # For file attachments


@dataclass
class CommandParam:
    """Definition of a command parameter."""

    name: str
    description: str
    type: type  # str, int, bool, etc.
    required: bool = True
    default: Any = None


class Gateway(ABC):
    """Abstract messaging gateway interface."""

    @abstractmethod
    async def start(self) -> None:
        """Start the gateway and begin listening for commands."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the gateway."""
        pass

    @abstractmethod
    async def send_message(self, message: Message) -> None:
        """Send a message to a channel."""
        pass

    @abstractmethod
    async def send_progress(self, channel_id: str, percent: int, description: str) -> None:
        """Send a progress update to a channel."""
        pass

    @abstractmethod
    async def request_confirmation(self, channel_id: str, prompt: str) -> bool:
        """Request user confirmation (Yes/No)."""
        pass

    @abstractmethod
    async def send_followup(
        self,
        interaction_ref: Any,
        content: str = "",
        file_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send a followup to an interaction."""
        pass

    @abstractmethod
    async def broadcast(self, message: str) -> None:
        """Broadcast a message to all connected contexts/channels.

        For Discord: Sends to system channel or default channel of connected guilds.
        For Console: Prints to stdout.
        For Web: Logs or pushes event.
        """
        pass

    @abstractmethod
    def register_command_group(self, name: str, description: str = "") -> None:
        """Register a command group (for subcommands)."""
        pass

    @abstractmethod
    def register_command(
        self,
        name: str,
        handler: Callable[[Command], Awaitable[None]],
        description: str = "",
        params: list[CommandParam] | None = None,
        group: str | None = None,
        requires_auth: bool = False,
        requires_admin: bool = False,
        requires_mfa: bool = False,
    ) -> None:
        """Register a command handler.

        Args:
            name: Command name
            handler: Async function to handle the command
            description: Help text
            params: List of command parameters
            group: Optional parent group name
            requires_auth: If True, checks for authorized user
            requires_admin: If True, checks for admin privileges
            requires_mfa: If True, checks for active MFA session
        """
        pass

    @abstractmethod
    def is_user_authorized(self, user_id: str) -> bool:
        """Check if a user is authorized to use the bot."""
        pass
