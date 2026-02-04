from unittest.mock import MagicMock

import pytest

from astra.adapters.gateways.discord.auth import AuthManager


@pytest.fixture
def auth_mgr():
    config = MagicMock()
    config.allowed_users = ["123"]
    # Mock admin list
    config.orchestration.security.admin_users = ["999"]
    return AuthManager(config)


def test_auth_manager_init(auth_mgr):
    assert "123" in auth_mgr.get_authorized_users()


def test_is_authorized(auth_mgr):
    # Allowed user
    assert auth_mgr.is_user_authorized("123")
    # Admin (implicitly allowed)
    assert auth_mgr.is_user_authorized("999")
    # Random
    assert not auth_mgr.is_user_authorized("456")


def test_is_admin(auth_mgr):
    assert auth_mgr.is_admin("999")
    assert not auth_mgr.is_admin("123")


def test_add_remove_user(auth_mgr):
    # Add
    assert auth_mgr.add_authorized_user("555")
    assert auth_mgr.is_user_authorized("555")
    assert not auth_mgr.add_authorized_user("555")  # Already there

    # Remove
    assert auth_mgr.remove_authorized_user("555")
    assert not auth_mgr.is_user_authorized("555")
    assert not auth_mgr.remove_authorized_user("555")  # Not there


def test_security_levels(auth_mgr):
    # Depending on implementation details, test different permission checks
    pass
