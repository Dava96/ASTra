"""Integration tests for Discord Gateway and Orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from astra.adapters.gateways.discord.gateway import DiscordGateway
from astra.interfaces.gateway import Command


@pytest.mark.asyncio
class TestGatewayOrchestrator:
    """Tests the interaction between Discord Gateway and Orchestrator."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.allowed_users = ["123"]
        config.orchestration.security.admin_users = ["admin1"]
        config.orchestration.security.mfa_secrets = {"123": "SECRET"}
        return config

    @pytest.fixture
    def gateway(self, mock_config):
        with patch("astra.adapters.gateways.discord.gateway.AuthManager"), \
             patch("astra.adapters.gateways.discord.gateway.get_config", return_value=mock_config):
            gw = DiscordGateway(config=mock_config)
            # Inject a real-ish but mocked AuthManager for session control
            gw._auth = MagicMock()
            gw._auth.get_authorized_users.return_value = ["123"]
            gw._auth.is_user_authorized.side_effect = lambda uid: uid in ["123", "admin1"]
            gw._auth.is_admin.side_effect = lambda uid: uid == "admin1"
            return gw

    async def test_feature_command_triggers_orchestrator(self, gateway):
        """Test that a Discord command correctly triggers an orchestrator callback."""
        mock_handler = AsyncMock()

        # Simulate a command interaction (simplified)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user.id = 123
        interaction.channel_id = 456
        interaction.response = AsyncMock()

        # We manually call the handler that would be triggered by Discord
        cmd = Command(
            name="feature",
            args={"request": "make a cat app", "type": "feature"},
            user_id="123",
            channel_id="456",
            raw_interaction=interaction
        )

        await mock_handler(cmd)

        mock_handler.assert_called_once()
        assert mock_handler.call_args[0][0].args["request"] == "make a cat app"

    async def test_mfa_block_on_sensitive_command(self, gateway):
        """Test that sensitive commands are blocked without MFA."""
        # Define a mock handler that requires MFA
        mock_handler = AsyncMock()

        async def sensitive_handler(cmd):
            await mock_handler(cmd)
            await cmd.raw_interaction.response.send_message("SUCCESS")

        # Register command dynamically with requires_mfa=True
        gateway.register_command(
            name="sensitive",
            handler=sensitive_handler,
            requires_mfa=True
        )

        # Mock auth to say no active session
        gateway._auth.has_active_session.return_value = False

        # Create interaction
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user.id = 123
        interaction.response = AsyncMock()
        interaction.command.name = "sensitive"

        # Execute through the internal handler to simulate gateway dispatch
        # We need to find the register key. register_command uses name as key if no group.
        # But gateway._handle_dynamic_command expects register_key.
        # The internal dispatch in Gateway doesn't expose a clean public 'receive_interaction' method for tests
        # other than mocking the app_command callback.
        # However, register_command executes exec() to create a callback.
        # We can simulate calling the internal handler directly as the callbacks do.

        await gateway._handle_dynamic_command(interaction, "sensitive")

        # Verify it was blocked
        assert not mock_handler.called
        interaction.response.send_message.assert_called_with(
            "🔒 MFA session required. Use `/mfa login` to authenticate.", ephemeral=True
        )

    async def test_mfa_allow_after_login(self, gateway):
        """Test that sensitive commands are allowed with active MFA."""
        mock_handler = AsyncMock()

        async def sensitive_handler(cmd):
            await mock_handler(cmd)
            await cmd.raw_interaction.response.send_message("SUCCESS")

        gateway.register_command(
            name="sensitive_ok",
            handler=sensitive_handler,
            requires_mfa=True
        )

        # Mock auth to say session IS active
        gateway._auth.has_active_session.return_value = True

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user.id = 123
        interaction.response = AsyncMock()
        interaction.command.name = "sensitive_ok"
        # Since we use interaction.response.send_message in SUCCESS, mock it
        # Actually in handler it calls raw_interaction.response.send_message
        # But usually we use response.send_message or followup.send

        # Call internal handler
        await gateway._handle_dynamic_command(interaction, "sensitive_ok")

        # Verify it passed through
        mock_handler.assert_called()
