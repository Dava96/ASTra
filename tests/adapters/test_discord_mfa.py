import time
from unittest.mock import AsyncMock, MagicMock, patch

import pyotp
import pytest

from astra.adapters.gateways.discord.auth import AuthManager
from astra.adapters.gateways.discord.commands import check_admin, check_mfa


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
        auth_manager._sessions[user_id] = time.time() - 10 # Expired

        assert auth_manager.has_active_session(user_id) is False
        assert user_id not in auth_manager._sessions

    def test_reset_mfa(self, auth_manager, mock_config):
        user_id = "user_1"
        auth_manager.get_mfa_secret(user_id)
        assert user_id in mock_config.orchestration.security.mfa_secrets

        auth_manager.reset_mfa(user_id)
        assert user_id not in mock_config.orchestration.security.mfa_secrets

class TestMFADecorators:
    @pytest.mark.asyncio
    async def test_check_mfa_decorator(self, auth_manager):
        mock_interaction = AsyncMock()
        mock_interaction.user.id = "123"

        # Set up global gateway instance for decorator
        with patch("astra.adapters.gateways.discord.commands.gateway_instance") as mock_gw:
            mock_gw._auth = auth_manager

            @check_mfa
            async def protected_cmd(interaction):
                await interaction.response.send_message("Success")

            # 1. No session
            auth_manager._sessions = {}
            await protected_cmd(mock_interaction)
            mock_interaction.response.send_message.assert_called_with(
                "🔒 MFA session required. Use `/mfa login` to authenticate.",
                ephemeral=True
            )

            # 2. Active session
            auth_manager.start_session("123")
            await protected_cmd(mock_interaction)
            assert mock_interaction.response.send_message.call_args[0][0] == "Success"

    @pytest.mark.asyncio
    async def test_check_admin_decorator_with_mfa(self, auth_manager):
        mock_interaction = AsyncMock()
        mock_interaction.user.id = "admin_id"

        with patch("astra.adapters.gateways.discord.commands.gateway_instance") as mock_gw:
            mock_gw._auth = auth_manager
            mock_gw.is_admin.side_effect = lambda uid: uid == "admin_id"

            @check_admin
            async def admin_cmd(interaction):
                await interaction.response.send_message("Admin Success")

            # 1. Admin but no MFA session
            auth_manager._sessions = {}
            await admin_cmd(mock_interaction)
            mock_interaction.response.send_message.assert_called_with(
                "🔒 Admin action requires MFA. Use `/mfa login` to authenticate.",
                ephemeral=True
            )

            # 2. Admin with MFA session
            auth_manager.start_session("admin_id")
            await admin_cmd(mock_interaction)
            assert mock_interaction.response.send_message.call_args[0][0] == "Admin Success"

            # 3. Not an admin
            mock_interaction.user.id = "regular_user"
            await admin_cmd(mock_interaction)
            mock_interaction.response.send_message.assert_called_with(
                "⛔ Admin only.", ephemeral=True
            )
