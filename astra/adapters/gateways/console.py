"""Console gateway for CLI interactions."""

import logging
from typing import Any

from astra.config import Config, get_config
from astra.interfaces.gateway import Gateway, Message

logger = logging.getLogger(__name__)


class ConsoleGateway(Gateway):
    """Gateway for terminal interaction.
    
    This gateway is used for local CLI development. Since it runs on the same
    machine as the server, all users are considered authorized.
    """

    def __init__(self, config: Config | None = None):
        self._config = config or get_config()

    async def start(self) -> None:
        """Start the console gateway (no-op)."""
        pass

    async def stop(self) -> None:
        """Stop the console gateway (no-op)."""
        pass

    async def send_message(self, message: Message) -> None:
        """Print message to stdout."""
        print(f"\n[{message.channel_id}] 🤖 ASTra:\n{message.content}")
        if message.file_path:
            print(f"[File attached: {message.file_path}]")

    async def send_progress(self, channel_id: str, percent: int, description: str) -> None:
        """Print progress update."""
        print(f"[{channel_id}] ⏳ {percent}% - {description}")

    async def request_confirmation(self, channel_id: str, prompt: str) -> bool:
        """Request confirmation via stdin."""
        print(f"\n{prompt}")
        response = input("Confirm? (y/N): ").strip().lower()
        return response == "y"

    async def get_history(self, channel_id: str, limit: int = 10) -> list[Message]:
        """Get history (not supported in console)."""
        return []

    async def send_followup(
        self,
        interaction_ref: Any,
        content: str = "",
        file_path: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Send a followup (print to console)."""
        print(f"\n[Followup] 🤖 ASTra:\n{content}")
        if file_path:
            print(f"[File attached: {file_path}]")

    def register_command(self, name: str, handler: Any, description: str = "") -> None:
        """Register command (no-op for CLI mode)."""
        pass

    def is_user_authorized(self, user_id: str) -> bool:
        """CLI user is always authorized (local access = full access)."""
        return True
