import json
import logging
import time
from pathlib import Path

import pyotp

from astra.config import Config

logger = logging.getLogger(__name__)


class AuthManager:
    """Manages user authorization for the Discord gateway."""

    def __init__(self, config: Config, config_path: str = "config.json"):
        self._config = config
        self._config_path = Path(config_path)
        # Transient session tracking: {user_id: expiry_timestamp}
        self._sessions: dict[str, float] = {}
        # Session duration (30 days)
        self.SESSION_DURATION = 30 * 24 * 3600

    def is_user_authorized(self, user_id: str) -> bool:
        """Check if a user is in the allowed list."""
        allowed = self._config.allowed_users
        if not allowed:
            # If no users configured, deny access
            return False
        return user_id in allowed

    def is_admin(self, user_id: str) -> bool:
        """Check if a user is an admin."""
        return user_id in self._config.orchestration.security.admin_users

    def has_active_session(self, user_id: str) -> bool:
        """Check if the user has an active authenticated session."""
        if user_id not in self._sessions:
            return False

        if time.time() > self._sessions[user_id]:
            del self._sessions[user_id]
            return False

        return True

    def start_session(self, user_id: str) -> None:
        """Start a new session for the user."""
        self._sessions[user_id] = time.time() + self.SESSION_DURATION

    def get_mfa_secret(self, user_id: str) -> str:
        """Get or generate an MFA secret for the user."""
        secrets = self._config.orchestration.security.mfa_secrets
        if user_id not in secrets:
            secrets[user_id] = pyotp.random_base32()
            self._save_config()
        return secrets[user_id]

    def verify_mfa(self, user_id: str, code: str) -> bool:
        """Verify an MFA code and start a session if valid."""
        secrets = self._config.orchestration.security.mfa_secrets
        if user_id not in secrets:
            return False

        totp = pyotp.TOTP(secrets[user_id])
        if totp.verify(code):
            self.start_session(user_id)
            return True
        return False

    def reset_mfa(self, user_id: str) -> None:
        """Reset MFA secret for a user."""
        secrets = self._config.orchestration.security.mfa_secrets
        if user_id in secrets:
            del secrets[user_id]
            self._save_config()

    def add_authorized_user(self, user_id: str) -> bool:
        """Add a user to the authorized list."""
        if user_id not in self._config.allowed_users:
            self._config.allowed_users.append(user_id)
            self._save_config()
            return True
        return False

    def remove_authorized_user(self, user_id: str) -> bool:
        """Remove a user from the authorized list."""
        if user_id in self._config.allowed_users:
            self._config.allowed_users.remove(user_id)
            self._save_config()
            return True
        return False

    def get_authorized_users(self) -> list[str]:
        """Get the list of authorized user IDs."""
        return self._config.allowed_users

    def _save_config(self) -> None:
        """Persist current auth state to config file."""
        if not self._config_path.exists():
            logger.warning(f"Config file {self._config_path} not found. skipping save.")
            return

        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))

            # Ensure orchestration.security structure exists
            if "orchestration" not in data:
                data["orchestration"] = {}
            if "security" not in data["orchestration"]:
                data["orchestration"]["security"] = {}

            # Update values
            data["orchestration"]["allowed_users"] = self._config.allowed_users
            data["orchestration"]["security"]["mfa_secrets"] = self._config.orchestration.security.mfa_secrets

            # Handle legacy root allowed_users if present
            if "allowed_users" in data:
                data["allowed_users"] = self._config.allowed_users

            self._config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save auth config to {self._config_path}: {e}")
