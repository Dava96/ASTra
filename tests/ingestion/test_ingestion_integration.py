"""Integration tests for Ingestion Engine wiring."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.handlers.command_handlers import CommandHandler
from astra.interfaces.gateway import Command


@pytest.fixture
def mock_gateway():
    return AsyncMock()

@pytest.fixture
def mock_orchestrator():
    orch = MagicMock()
    orch.get_active_project.return_value = None
    orch._vector_store = MagicMock()
    orch._vector_store.get_collection_stats.return_value = {"count": 0}
    return orch

@pytest.fixture
def mock_queue():
    return MagicMock()

@pytest.fixture
def mock_config():
    config = MagicMock()
    # Return appropriate values for different config paths
    def mock_get(*args, default=None):
        if args == ("ingestion", "ignore_patterns"):
            return []
        if args == ("ingestion", "safe_branches"):
            return ["main", "master"]
        return default
    config.get = MagicMock(side_effect=mock_get)
    return config

@pytest.fixture
def command_handler(mock_gateway, mock_orchestrator, mock_queue, mock_config):
    return CommandHandler(mock_gateway, mock_orchestrator, mock_queue, mock_config)

@pytest.mark.asyncio
async def test_checkout_integrates_knowledge_graph(command_handler, mock_gateway):
    """Test that checkout triggers background ingestion."""

    cmd = Command(
        name="checkout",
        args={"request": "https://github.com/test/repo"},
        user_id="user1",
        channel_id="chan1",
        raw_interaction=MagicMock()
    )

    # Mock Safeguard in project_handlers
    with patch("astra.handlers.project_handlers.Safeguard") as MockSafe:
        safe_instance = MockSafe.return_value
        safe_instance.check_repo_size.return_value = (True, "OK")
        safe_instance.check_system_resources.return_value = (True, "OK")

        # Mock VCS
        with patch("astra.handlers.project_handlers.GitHubVCS") as MockVCS:
            vcs = MockVCS.return_value
            # Return a simple Result object with success=True
            clone_res = MagicMock()
            clone_res.success = True
            vcs.clone = AsyncMock(return_value=clone_res)
            vcs.get_current_branch = AsyncMock(return_value="main")

            # Mock IngestionPipeline
            with patch("astra.ingestion.pipeline.IngestionPipeline") as MockPipeline:
                pipeline = MockPipeline.return_value
                pipeline.run_async = AsyncMock(return_value=100)

                await command_handler.handle_checkout(cmd)

                # Allow background task to start
                import asyncio
                await asyncio.sleep(0.1)

                # Verify Pipeline interaction
                MockPipeline.assert_called_once()
                pipeline.run_async.assert_called_once()

                # Verify User Feedback
                assert mock_gateway.send_followup.call_count >= 1
