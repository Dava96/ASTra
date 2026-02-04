
import os
from unittest.mock import MagicMock, patch

import pytest

from astra.setup_wizard import _save_env_file, run_setup_wizard


@pytest.fixture
def mock_console():
    with patch("astra.setup_wizard.console") as mock:
        yield mock

@pytest.fixture
def mock_prompt():
    with patch("astra.setup_wizard.Prompt") as mock:
        yield mock

@pytest.fixture
def mock_confirm():
    with patch("astra.setup_wizard.Confirm") as mock:
        yield mock

@pytest.fixture
def mock_requests():
    with patch("astra.setup_wizard.requests") as mock:
        yield mock

@pytest.fixture
def mock_shutil():
    with patch("astra.setup_wizard.shutil") as mock:
        yield mock

@pytest.fixture
def mock_config(tmp_path):
    # Use a pure MagicMock to avoid Pydantic "no field 'save'" errors
    config = MagicMock()

    # Setup default values expected by the wizard
    config.orchestration.security.admin_users = []
    config.orchestration.security.mfa_secrets = {}
    config.llm.model = "default"
    config.llm.host = "http://localhost:11434"
    config.skills_mp.enabled = False
    config.skills_mp.api_key = None
    config.git.auto_pr = True
    config.scheduler.enabled = True

    # Mock list behaviors
    config.orchestration.security.command_allowlist = ["git"]

    with patch("astra.setup_wizard.get_config", return_value=config):
        yield config

def test_save_env_file(tmp_path):
    # Test creating new .env
    with patch("astra.setup_wizard.Path") as mock_path:
        mock_file = MagicMock()
        mock_path.return_value = mock_file
        mock_file.exists.return_value = False

        secrets = {"TOKEN": "123", "KEY": "abc"}
        _save_env_file(secrets)

        args = mock_file.write_text.call_args[0][0]
        assert "TOKEN=123" in args
        assert "KEY=abc" in args

def test_save_env_file_update(tmp_path):
    # Test updating existing .env
    with patch("astra.setup_wizard.Path") as mock_path:
        mock_file = MagicMock()
        mock_path.return_value = mock_file
        mock_file.exists.return_value = True
        mock_file.read_text.return_value = "OLD=foo\nTOKEN=old_token\n"

        secrets = {"TOKEN": "new_token"}
        _save_env_file(secrets)

        args = mock_file.write_text.call_args[0][0]
        assert "OLD=foo" in args
        assert "TOKEN=new_token" in args

def test_wizard_run_flow(mock_console, mock_prompt, mock_confirm, mock_config, mock_requests, mock_shutil):
    # Setup user inputs
    # 1. Discord Token (No env var set initially)
    with patch.dict(os.environ, {}, clear=True):
        # Setup Mocks
        mock_shutil.which.return_value = True # Git detected

        # Ollama Mock
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "llama3:latest"}, {"name": "qwen:7b"}]}
        mock_requests.get.return_value = mock_resp

        # Sequence of Prompts:
        # 1. Discord Token -> "invalid_token_format" (Validation fails/warns)
        # 2. Admin IDs -> "admin1, admin2"
        # 3. LLM Provider -> "ollama"
        # 4. Ollama Host -> "http://local:11434"
        # 5. Select Model -> "llama3:latest" (from auto-detected list)
        # 6. SkillsMP Key -> "mp_key_xyz"

        mock_prompt.ask.side_effect = [
            "invalid_token_format", # Discord (Will trigger confirmation)
            "admin1, admin2",       # Admins
            "ollama",               # Provider
            "http://local:11434",   # Host
            "llama3:latest",        # Select Model
            "mp_key_xyz",           # SkillsMP Key
        ]

        # Sequence of Confirms:
        # 1. Token format unusual? -> True (Use anyway)
        # 2. Update Admins? -> True (wait, logic: if not admins or Confirm...)
        #    admins is empty, so it enters block directly without Confirm.
        #    Wait, `if not current_admins` is True. Short-circuit OR.
        #    So Confirm is skipped.
        # 3. Enable SkillsMP? -> True
        # 4. Update SkillsMP Key? -> True (key is None, short-circuit OR?)
        #    `if not current_key` (True). Short circuit. Confirm Skipped.
        # 5. Enable Auto-PR? -> False
        # 6. Enable Scheduler? -> True
        # 7. Enable WebUI? -> False

        mock_confirm.ask.side_effect = [
            True,  # Token unusual, use anyway
            True,  # Enable SkillsMP
            False, # Git AutoPR
            True,  # Scheduler
            False, # WebUI Gateway
        ]

        # Patch Path to redirect .env writes to tmp_path
        with patch("astra.setup_wizard.Path") as mock_path_cls:
            mock_env_path = MagicMock()
            mock_path_cls.return_value = mock_env_path
            # Mock exists() to False so it doesn't try to read real .env
            mock_env_path.exists.return_value = False

            run_setup_wizard()

        # Verifications
        assert mock_config.orchestration.security.admin_users == ["admin1", "admin2"]
        # Logic: if not startswith "ollama", prefix "ollama_chat/". "llama3:latest" -> "ollama_chat/llama3:latest"
        assert mock_config.llm.model == "ollama_chat/llama3:latest"
        assert mock_config.llm.host == "http://local:11434"
        assert mock_config.skills_mp.enabled is True
        assert mock_config.skills_mp.api_key == "mp_key_xyz"
        assert mock_config.git.auto_pr is False
        assert mock_config.scheduler.enabled is True

        # Verify Git check
        mock_shutil.which.assert_called_with("git")

        # Verify Ollama Check
        mock_requests.get.assert_called()
