import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.core.template_manager import TemplateManager
from astra.interfaces.gateway import Message


@pytest.mark.asyncio
class TestTemplateAcquisition:
    """Integration test for TemplateManager's remote acquisition flow."""

    @pytest.fixture
    def mock_gateway(self):
        gateway = MagicMock()
        gateway.send_message = AsyncMock()
        gateway.request_confirmation = AsyncMock(return_value=True)
        return gateway

    @pytest.fixture
    def template_manager(self, tmp_path, mock_gateway):
        # We need to mock RemoteTemplateProvider because it makes actual HTTP requests
        with patch("astra.core.template_manager.RemoteTemplateProvider") as mock_provider_cls:
            mock_provider = mock_provider_cls.return_value
            mock_provider.is_enabled.return_value = True
            mock_provider.search.return_value = [
                {"name": "test_skill", "description": "A test skill", "id": "skill-123"}
            ]
            mock_provider.fetch_content.return_value = "---\nname: python_conventions\n---\n# Python Rules"

            tm = TemplateManager(template_dir=tmp_path, gateway=mock_gateway)
            tm._remote = mock_provider
            return tm

    async def test_acquisition_flow_success(self, template_manager, mock_gateway, tmp_path):
        """Test a full successful acquisition of a missing template."""
        # 1. Trigger detection for a project that would need python_conventions.md
        # but it doesn't exist yet in tmp_path.
        project_path = tmp_path / "mock_project"
        project_path.mkdir()
        (project_path / "requirements.txt").write_text("python")

        with patch("astra.core.template_manager.get_manifest_files_for_project", return_value={"requirements.txt": "python"}):
            # This should trigger _propose_template_acquisition in a background task
            template_manager.get_context_file_paths(project_path, channel_id="chan1")

            # Wait for background task to complete (it's fired via loop.create_task)
            # In tests, we need to be careful. Let's wait a bit or gather tasks.
            await asyncio.sleep(1.0)

            # 2. Verify gateway interactions
            # Should have searched SkillsMP and sent search results
            mock_gateway.send_message.assert_any_call(
                pytest.match_message("ℹ️ Missing required template: `python_conventions.md`")
            )

            # Should have asked for confirmation to inspect
            mock_gateway.request_confirmation.assert_any_call(
                "chan1", pytest.match_regex("Found skill: .*test_skill.*")
            )

            # Should have shown preview
            mock_gateway.send_message.assert_any_call(
                pytest.match_message("## Preview: python_conventions.md")
            )

            # Should have asked for security confirmation
            mock_gateway.request_confirmation.assert_any_call(
                "chan1", "⚠️ **Security Check**: Do you approve this content for installation?"
            )

            # 3. Verify file was actually created/updated
            installed_path = tmp_path / "python_conventions.md"
            assert installed_path.exists()
            assert "# Python Rules" in installed_path.read_text()

    async def test_acquisition_flow_cancelled_by_user(self, template_manager, mock_gateway, tmp_path):
        """Test acquisition cancelled by user at inspection stage."""
        mock_gateway.request_confirmation.side_effect = [False] # User says NO to inspect

        project_path = tmp_path / "mock_project_2"
        project_path.mkdir()
        (project_path / "requirements.txt").write_text("python")

        with patch("astra.core.template_manager.get_manifest_files_for_project", return_value={"requirements.txt": "python"}):
            template_manager.get_context_file_paths(project_path, channel_id="chan2")
            await asyncio.sleep(1.0)

            # Should NOT have reached second confirmation or fetch
            assert mock_gateway.request_confirmation.call_count == 1
            assert not (tmp_path / "python_conventions.md").exists()

# Custom matcher for pytest.assert_any_call with Message objects
class MessageMatcher:
    def __init__(self, content_pattern, is_regex=False):
        self.content_pattern = content_pattern
        self.is_regex = is_regex

    def __eq__(self, other):
        if isinstance(other, Message):
            content = other.content
        elif isinstance(other, str):
            content = other
        else:
            return False

        if self.is_regex:
            import re
            return re.search(self.content_pattern, content) is not None
        return self.content_pattern in content

    def __repr__(self):
        return f"MessageMatcher(pattern='{self.content_pattern}')"

def pytest_match_message(pattern):
    return MessageMatcher(pattern)

def pytest_match_regex(pattern):
    return MessageMatcher(pattern, is_regex=True)

# Patching pytest for convenience in this file
pytest.match_message = pytest_match_message
pytest.match_regex = pytest_match_regex
