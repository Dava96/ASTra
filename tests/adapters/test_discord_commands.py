"""Tests for dynamic command registration in Discord Gateway."""

from unittest.mock import MagicMock, patch

import pytest

GATEWAY_MODULE = "astra.adapters.gateways.discord.gateway"

class TestCommandRegistration:
    """Test dynamic command registration."""

    @pytest.mark.asyncio
    async def test_register_command_basic(self):
        """Test registering a simple command."""
        config = MagicMock()
        config.allowed_users = ["123"]

        with (
            patch.dict("os.environ", {"DISCORD_TOKEN": "test_token"}),
            patch(f"{GATEWAY_MODULE}.discord.Client"),
            patch(f"{GATEWAY_MODULE}.app_commands.CommandTree") as MockTree,
            patch(f"{GATEWAY_MODULE}.get_config", return_value=config),
        ):
            from astra.adapters.gateways.discord.gateway import DiscordGateway

            gateway = DiscordGateway(config)
            mock_tree = MockTree.return_value

            async def dummy_handler(cmd):
                pass

            gateway.register_command(
                name="test_cmd",
                handler=dummy_handler,
                description="Test Description"
            )

            # Check if command was added to tree
            mock_tree.add_command.assert_called_once()
            call_args = mock_tree.add_command.call_args[0][0]

            assert call_args.name == "test_cmd"
            assert call_args.description == "Test Description"

            # Verify handler is stored
            assert "test_cmd" in gateway._handlers
            assert gateway._handlers["test_cmd"] == dummy_handler

    @pytest.mark.asyncio
    async def test_register_command_with_params(self):
        """Test registering a command with parameters."""
        config = MagicMock()
        config.allowed_users = ["123"]

        with (
            patch.dict("os.environ", {"DISCORD_TOKEN": "test_token"}),
            patch(f"{GATEWAY_MODULE}.discord.Client"),
            patch(f"{GATEWAY_MODULE}.app_commands.CommandTree") as MockTree,
            patch(f"{GATEWAY_MODULE}.get_config", return_value=config),
        ):
            from astra.adapters.gateways.discord.gateway import DiscordGateway
            from astra.interfaces.gateway import CommandParam

            gateway = DiscordGateway(config)
            mock_tree = MockTree.return_value

            async def dummy_handler(cmd):
                pass

            params = [
                CommandParam(name="arg1", description="desc1", type=str),
                CommandParam(name="arg2", description="desc2", type=int, required=False),
            ]

            gateway.register_command(
                name="param_cmd",
                handler=dummy_handler,
                params=params
            )

            mock_tree.add_command.assert_called_once()
            cmd_obj = mock_tree.add_command.call_args[0][0]

            # Inspect callback annotations
            annotations = cmd_obj.callback.__annotations__
            assert annotations["arg1"] is str
            # Optional int might be int | None
            assert annotations["arg2"] == int | None

    @pytest.mark.asyncio
    async def test_register_command_group(self):
        """Test registering a command group."""
        config = MagicMock()

        with (
            patch.dict("os.environ", {"DISCORD_TOKEN": "test_token"}),
            patch(f"{GATEWAY_MODULE}.discord.Client"),
            patch(f"{GATEWAY_MODULE}.app_commands.CommandTree") as MockTree,
            patch(f"{GATEWAY_MODULE}.get_config", return_value=config),
        ):
            from astra.adapters.gateways.discord.gateway import DiscordGateway

            gateway = DiscordGateway(config)
            mock_tree = MockTree.return_value
            # Mock get_commands to return empty list initially
            mock_tree.get_commands.return_value = []

            gateway.register_command_group("test_group", "Group Desc")

            mock_tree.add_command.assert_called_once()
            group_obj = mock_tree.add_command.call_args[0][0]
            # Since we can't easily import app_commands.Group to compare types without real discord.py logic,
            # we just check the name/desc attributes which mocks should capture if it's an object,
            # BUT app_commands.Group is a real class if we import it.
            # However, we are patching app_commands.CommandTree, but we are using real app_commands.Group inside `register_command_group`?
            # Yes, `register_command_group` calls `app_commands.Group(...)`.
            # Since we didn't patch `app_commands.Group`, it will use the real one (if installed) or fail if we didn't mock `app_commands` module entirely.
            # In `gateway.py`, it imports `from discord import app_commands`.
            # We patched `GATEWAY_MODULE.app_commands.CommandTree`.
            # We probably need to verify that `app_commands.Group` is working.

            assert group_obj.name == "test_group"
            assert group_obj.description == "Group Desc"
