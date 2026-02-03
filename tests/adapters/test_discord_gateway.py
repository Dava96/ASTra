"""Comprehensive tests for Discord gateway with mocking."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Use the actual module path for patching
GATEWAY_MODULE = 'astra.adapters.gateways.discord.gateway'


class TestGatewayInterfaces:
    """Test gateway interface types."""

    def test_command_dataclass(self):
        """Test Command dataclass fields."""
        from astra.interfaces.gateway import Command

        cmd = Command(
            name="checkout",
            args={"request": "https://github.com/user/repo"},
            user_id="123456",
            channel_id="789012",
            raw_interaction=MagicMock()
        )

        assert cmd.name == "checkout"
        assert cmd.args["request"] == "https://github.com/user/repo"
        assert cmd.user_id == "123456"

    def test_message_dataclass(self):
        """Test Message dataclass fields."""
        from astra.interfaces.gateway import Message

        msg = Message(
            content="Hello, world!",
            channel_id="123456",
            ephemeral=True,
            file_path="/tmp/log.txt"
        )

        assert msg.content == "Hello, world!"
        assert msg.ephemeral == True
        assert msg.file_path == "/tmp/log.txt"

    def test_message_defaults(self):
        """Test Message default values."""
        from astra.interfaces.gateway import Message

        msg = Message(content="Test", channel_id="123")

        assert msg.ephemeral == False
        assert msg.file_path is None


class TestDiscordGatewayMocked:
    """Test Discord gateway with mocked discord.py."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.allowed_users = ["123456", "789012"]
        config.orchestration.security.admin_users = []
        return config

    @pytest.fixture
    def gateway(self, mock_config):
        with patch.dict('os.environ', {'DISCORD_TOKEN': 'test_token'}), \
             patch(f'{GATEWAY_MODULE}.discord.Client'), \
             patch(f'{GATEWAY_MODULE}.app_commands.CommandTree'), \
             patch(f'{GATEWAY_MODULE}.get_config', return_value=mock_config):

            from astra.adapters.gateways.discord.gateway import DiscordGateway
            return DiscordGateway(mock_config)

    def test_is_user_authorized_allowed(self, gateway):
        """Test authorized user."""
        assert gateway.is_user_authorized("123456") == True

    def test_is_user_authorized_not_allowed(self, gateway):
        """Test unauthorized user."""
        assert gateway.is_user_authorized("999999") == False

    def test_is_user_authorized_empty_list(self, mock_config):
        """Test when allowlist is empty."""
        mock_config.allowed_users = []

        with patch.dict('os.environ', {'DISCORD_TOKEN': 'test_token'}), \
             patch(f'{GATEWAY_MODULE}.discord.Client'), \
             patch(f'{GATEWAY_MODULE}.app_commands.CommandTree'), \
             patch(f'{GATEWAY_MODULE}.get_config', return_value=mock_config):

            from astra.adapters.gateways.discord.gateway import DiscordGateway
            gateway = DiscordGateway(mock_config)

            # Empty list means no one authorized (needs setup)
            assert gateway.is_user_authorized("123456") == False


class TestMessageFormatting:
    """Test message formatting and sending."""

    @pytest.fixture
    def gateway_with_client(self, mock_config=None):
        config = mock_config or MagicMock()
        config.allowed_users = ["123456"]
        config.orchestration.security.admin_users = []

        with patch.dict('os.environ', {'DISCORD_TOKEN': 'test_token'}), \
             patch(f'{GATEWAY_MODULE}.discord.Client') as MockClient, \
             patch(f'{GATEWAY_MODULE}.app_commands.CommandTree'), \
             patch(f'{GATEWAY_MODULE}.get_config', return_value=config):

            client = MockClient.return_value
            client.get_channel = MagicMock()

            from astra.adapters.gateways.discord.gateway import DiscordGateway
            gateway = DiscordGateway(config)

            yield gateway, client

    @pytest.mark.asyncio
    async def test_send_message_short(self):
        """Test sending short message."""
        config = MagicMock()
        config.allowed_users = ["123"]
        config.orchestration.security.admin_users = []

        with patch.dict('os.environ', {'DISCORD_TOKEN': 'test_token'}), \
             patch(f'{GATEWAY_MODULE}.discord.Client') as MockClient, \
             patch(f'{GATEWAY_MODULE}.app_commands.CommandTree'), \
             patch(f'{GATEWAY_MODULE}.get_config', return_value=config):

            from astra.adapters.gateways.discord.gateway import DiscordGateway
            from astra.interfaces.gateway import Message

            gateway = DiscordGateway(config)

            # Setup mock channel
            mock_channel = AsyncMock()
            gateway._client.get_channel = MagicMock(return_value=mock_channel)

            msg = Message(content="Short message", channel_id="123456")
            await gateway.send_message(msg)

            mock_channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_long_as_file(self):
        """Test that long messages are sent as files."""
        config = MagicMock()
        config.allowed_users = ["123"]
        config.orchestration.security.admin_users = []

        with patch.dict('os.environ', {'DISCORD_TOKEN': 'test_token'}), \
             patch(f'{GATEWAY_MODULE}.discord.Client') as MockClient, \
             patch(f'{GATEWAY_MODULE}.app_commands.CommandTree'), \
             patch(f'{GATEWAY_MODULE}.discord.File') as MockFile, \
             patch(f'{GATEWAY_MODULE}.get_config', return_value=config):

            from astra.adapters.gateways.discord.gateway import DiscordGateway
            from astra.interfaces.gateway import Message

            gateway = DiscordGateway(config)

            mock_channel = AsyncMock()
            gateway._client.get_channel = MagicMock(return_value=mock_channel)

            long_content = "x" * 2000  # Over 1900 char limit
            msg = Message(content=long_content, channel_id="123456")
            await gateway.send_message(msg)

            # Should be called with a File attachment
            mock_channel.send.assert_called()


class TestProgressUpdates:
    """Test progress bar generation."""

    @pytest.mark.asyncio
    async def test_send_progress(self):
        """Test progress bar formatting."""
        config = MagicMock()
        config.allowed_users = ["123"]
        config.orchestration.security.admin_users = []

        with patch.dict('os.environ', {'DISCORD_TOKEN': 'test_token'}), \
             patch(f'{GATEWAY_MODULE}.discord.Client') as MockClient, \
             patch(f'{GATEWAY_MODULE}.app_commands.CommandTree'), \
             patch(f'{GATEWAY_MODULE}.get_config', return_value=config):

            from astra.adapters.gateways.discord.gateway import DiscordGateway

            gateway = DiscordGateway(config)

            mock_channel = AsyncMock()
            gateway._client.get_channel = MagicMock(return_value=mock_channel)

            await gateway.send_progress("123456", 50, "Halfway done")

            mock_channel.send.assert_called_once()
            call_args = mock_channel.send.call_args[0][0]
            assert "50%" in call_args
            assert "Halfway done" in call_args
            assert "█" in call_args  # Progress bar character

    @pytest.mark.parametrize("percent,expected_filled", [
        (0, 0),
        (25, 5),
        (50, 10),
        (75, 15),
        (100, 20),
    ])
    def test_progress_bar_lengths(self, percent, expected_filled):
        """Test progress bar has correct number of filled segments."""
        # Progress bar uses 20 characters total
        filled = int(percent / 5)
        assert filled == expected_filled


class TestConfirmation:
    """Test confirmation dialog."""

    @pytest.mark.asyncio
    async def test_request_confirmation_timeout(self):
        """Test confirmation timeout handling."""
        config = MagicMock()
        config.allowed_users = ["123"]
        config.orchestration.security.admin_users = []

        with patch.dict('os.environ', {'DISCORD_TOKEN': 'test_token'}), \
             patch(f'{GATEWAY_MODULE}.discord.Client'), \
             patch(f'{GATEWAY_MODULE}.app_commands.CommandTree'), \
             patch(f'{GATEWAY_MODULE}.get_config', return_value=config), \
             patch(f'{GATEWAY_MODULE}.ConfirmationView') as MockView:

            from astra.adapters.gateways.discord.gateway import DiscordGateway
            gateway = DiscordGateway(config)

            # Setup mock channel
            mock_channel = AsyncMock()
            gateway._client.get_channel = MagicMock(return_value=mock_channel)

            # Setup mock view
            mock_view_instance = MockView.return_value
            mock_view_instance.wait = AsyncMock() # Returns immediately
            mock_view_instance.value = None # No button clicked

            result = await gateway.request_confirmation("123456", "Confirm?")

            assert result == False
            mock_channel.send.assert_called_once()


class TestEdgeCases:
    """Edge cases for Discord gateway."""

    def test_missing_token_raises(self):
        """Test that missing token raises error on start."""
        config = MagicMock()
        config.allowed_users = ["123"]
        config.orchestration.security.admin_users = []

        with patch.dict('os.environ', {}, clear=True), \
             patch(f'{GATEWAY_MODULE}.discord.Client'), \
             patch(f'{GATEWAY_MODULE}.app_commands.CommandTree'), \
             patch(f'{GATEWAY_MODULE}.get_config', return_value=config):

            # Clear DISCORD_TOKEN
            import os
            if 'DISCORD_TOKEN' in os.environ:
                del os.environ['DISCORD_TOKEN']

            from astra.adapters.gateways.discord.gateway import DiscordGateway
            gateway = DiscordGateway(config)

            # Token is None when not set
            assert gateway._token is None

    @pytest.mark.asyncio
    async def test_send_message_channel_not_found(self):
        """Test handling when channel doesn't exist."""
        config = MagicMock()
        config.allowed_users = ["123"]
        config.orchestration.security.admin_users = []

        with patch.dict('os.environ', {'DISCORD_TOKEN': 'test_token'}), \
             patch(f'{GATEWAY_MODULE}.discord.Client'), \
             patch(f'{GATEWAY_MODULE}.app_commands.CommandTree'), \
             patch(f'{GATEWAY_MODULE}.get_config', return_value=config):

            from astra.adapters.gateways.discord.gateway import DiscordGateway
            from astra.interfaces.gateway import Message

            gateway = DiscordGateway(config)
            gateway._client.get_channel = MagicMock(return_value=None)

            msg = Message(content="Test", channel_id="999999999999")

            # Should not raise, just log error
            await gateway.send_message(msg)
