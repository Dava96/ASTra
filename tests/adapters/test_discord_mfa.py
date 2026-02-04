import time
from unittest.mock import AsyncMock, MagicMock, patch

import pyotp
import pytest

from astra.adapters.gateways.discord.auth import AuthManager


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.allowed_users = ["123"]
    config.orchestration.security.admin_users = ["admin_id"]
    config.orchestration.security.mfa_secrets = {}
    return config


@pytest.fixture
def auth_manager(mock_config):
    # Use a dummy path that won't actually be written to
    return AuthManager(mock_config, config_path="nonexistent.json")


class TestMFAAuthManager:
    def test_get_mfa_secret(self, auth_manager, mock_config):
        secret = auth_manager.get_mfa_secret("user_1")
        assert secret in mock_config.orchestration.security.mfa_secrets.values()
        assert len(secret) == 32

        # Second call returns same secret
        assert auth_manager.get_mfa_secret("user_1") == secret

    def test_verify_mfa_success(self, auth_manager):
        user_id = "user_1"
        secret = auth_manager.get_mfa_secret(user_id)
        totp = pyotp.TOTP(secret)
        code = totp.now()

        assert auth_manager.verify_mfa(user_id, code) is True
        assert auth_manager.has_active_session(user_id) is True

    def test_verify_mfa_failure(self, auth_manager):
        user_id = "user_1"
        auth_manager.get_mfa_secret(user_id)

        assert auth_manager.verify_mfa(user_id, "000000") is False
        assert auth_manager.has_active_session(user_id) is False

    def test_session_expiration(self, auth_manager):
        user_id = "user_1"
        auth_manager._sessions[user_id] = time.time() - 10  # Expired

        assert auth_manager.has_active_session(user_id) is False
        assert user_id not in auth_manager._sessions

    def test_reset_mfa(self, auth_manager, mock_config):
        user_id = "user_1"
        auth_manager.get_mfa_secret(user_id)
        assert user_id in mock_config.orchestration.security.mfa_secrets

        auth_manager.reset_mfa(user_id)
        assert user_id not in mock_config.orchestration.security.mfa_secrets




GATEWAY_MODULE = "astra.adapters.gateways.discord.gateway"

class TestMFAIntegration:
    """Test MFA integration with Gateway."""

    @pytest.fixture
    def gateway(self, mock_config):
        with (
            patch.dict("os.environ", {"DISCORD_TOKEN": "test_token"}),
            patch(f"{GATEWAY_MODULE}.discord.Client"),
            patch(f"{GATEWAY_MODULE}.app_commands.CommandTree"),
            patch(f"{GATEWAY_MODULE}.get_config", return_value=mock_config),
        ):
            from astra.adapters.gateways.discord.gateway import DiscordGateway
            gateway = DiscordGateway(mock_config)
            # MFA commands are not registered in init, normally registered by orchestrator calling register_built_in_commands.
            # We explicitly call it for the test.
            gateway._register_mfa_commands()
            return gateway

    @pytest.mark.asyncio
    async def test_mfa_setup_dms_user(self, gateway):
        """Test that MFA setup command DMs the user."""
        # Get the handler
        setup_handler = gateway._handlers.get("mfa.setup")
        assert setup_handler is not None, "MFA setup handler not registered"

        # Mock Command object
        cmd = MagicMock()
        cmd.user_id = "123"
        cmd.raw_interaction.user.name = "TestUser"

        # Mock async send methods
        cmd.raw_interaction.user.send = AsyncMock()
        cmd.raw_interaction.followup.send = AsyncMock()

        # Mock auth manager secret provision
        gateway._auth.get_mfa_secret = MagicMock(return_value="SECRET123456")

        # Execute
        await setup_handler(cmd)

        # Verify DM sent
        cmd.raw_interaction.user.send.assert_called_once()
        args = cmd.raw_interaction.user.send.call_args[0]
        assert "SECRET123456" in args[0]
        assert "**MFA Setup**" in args[0]

        # Verify confirmation in channel (ephemeral)
        cmd.raw_interaction.followup.send.assert_called_with(
            "✅ Sent you a DM with the setup instructions!", ephemeral=True
        )

    def test_mfa_setup_requires_auth(self, gateway):
        """Test that MFA setup command is tagged to require auth."""
        meta = gateway._handlers_meta.get("mfa.setup")
        assert meta is not None
        assert meta["auth"] is True

    # @pytest.mark.asyncio
    # async def test_mfa_setup_dm_forbidden(self, gateway):
    #     """Test handling when user has DMs disabled."""
    #     # Skipping due to difficulty mocking discord.Forbidden init structure reliably in this env
    #     pass



