"""Tests for Setup Wizard."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from astra.setup_wizard import run_setup_wizard


class TestSetupWizard:
    @pytest.fixture
    def mock_console(self):
        with patch("astra.setup_wizard.console") as mock:
            yield mock

    @pytest.fixture
    def mock_prompt(self):
        with patch("astra.setup_wizard.Prompt") as mock:
            yield mock

    @pytest.fixture
    def mock_confirm(self):
        with patch("astra.setup_wizard.Confirm") as mock:
            yield mock

    def test_run_wizard_new_install(self, mock_console, mock_prompt, mock_confirm, tmp_path):
        """Test wizard flow for fresh install."""
        # Mock inputs
        mock_prompt.ask.side_effect = [
            "test_token",       # Discord Token
            "123456",           # Admin User
            "ollama",           # LLM Provider
            "qwen2.5-coder:7b"  # Model Name
        ]

        # Change CWD to tmp_path to avoid writing to real files
        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            run_setup_wizard()

            # Verify .env
            env = Path(".env").read_text(encoding="utf-8")
            assert "DISCORD_TOKEN=test_token" in env

            # Verify config.json
            config = json.loads(Path("config.json").read_text(encoding="utf-8"))
            assert config["orchestration"]["security"]["admin_users"] == ["123456"]
            assert config["llm"]["model"] == "ollama/qwen2.5-coder:7b"

        finally:
            os.chdir(cwd)

    def test_run_wizard_openai(self, mock_console, mock_prompt, mock_confirm, tmp_path):
        """Test wizard flow for OpenAI."""
        # Mock inputs
        mock_prompt.ask.side_effect = [
            "test_token",       # Discord Token
            "admin_id",         # Admin User
            "openai",           # LLM Provider
            "gpt-4o",           # Model Name
            "sk-proj-123"       # API Key
        ]

        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            run_setup_wizard()

            env = Path(".env").read_text(encoding="utf-8")
            assert "OPENAI_API_KEY=sk-proj-123" in env

            config = json.loads(Path("config.json").read_text(encoding="utf-8"))
            assert config["llm"]["model"] == "gpt-4o"
        finally:
            os.chdir(cwd)

    def test_overwrite_existing(self, mock_console, mock_prompt, mock_confirm, tmp_path):
        """Test wizard handles existing files."""
        # Setup existing
        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            Path(".env").write_text("DISCORD_TOKEN=old", encoding="utf-8")

            # Mock inputs
            # 1. Confirm update token? Yes
            # 2. Token input
            # 3. Admin user
            # 4. LLM provider
            # 5. Model
            # 6. Overwrite .env? Yes

            mock_confirm.ask.side_effect = [True, True] # Update existing token, Overwrite .env
            mock_prompt.ask.side_effect = [
                "new_token",
                "admin",
                "ollama",
                "model"
            ]

            # Patch os.getenv to simulate existing
            with patch.dict(os.environ, {"DISCORD_TOKEN": "old"}):
                run_setup_wizard()

            env = Path(".env").read_text(encoding="utf-8")
            assert "DISCORD_TOKEN=new_token" in env

        finally:
            os.chdir(cwd)
