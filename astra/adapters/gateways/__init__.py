"""Gateway adapters package.

This package provides a unified gateway interface with multiple implementations:
- ConsoleGateway: Interactive CLI interface for local development
- DiscordGateway: Discord bot interface for remote access

Usage:
    from astra.adapters.gateways import ConsoleGateway, DiscordGateway
"""

from astra.adapters.gateways.console import ConsoleGateway
from astra.adapters.gateways.discord import DiscordGateway

__all__ = ["ConsoleGateway", "DiscordGateway"]
