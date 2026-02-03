"""Tests for Cloud Model Fallback logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.config import Config
from astra.core.orchestrator import Orchestrator
from astra.core.task_queue import TaskQueue


@pytest.fixture
def mock_gateway():
    return AsyncMock()

@pytest.fixture
def mock_config():
    # Use real config to avoid mock attribute issues
    config = Config()
    config.orchestration.fallback_to_cloud = True
    config.orchestration.fallback_model = "openai/gpt-4o"
    config.llm.model = "ollama/deepseek-coder"
    return config

@pytest.fixture
def orchestrator(mock_gateway, mock_config):
    return Orchestrator(mock_gateway, mock_config)

@pytest.mark.asyncio
async def test_fallback_flow(orchestrator, mock_gateway, mock_config, tmp_path):
    """Test full fallback flow: Failure -> Confirmation -> Escalation -> Retry."""
    from types import SimpleNamespace

    # Create a real directory for the mock project_path
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Setup context using SimpleNamespace to avoid MagicMock spec issues
    task = SimpleNamespace(id="task_1", channel_id="channel_1", request="Test Task")
    context = SimpleNamespace(
        task=task,
        attempts=3,
        errors=["Error 1", "Error 2", "Final Error"],
        phase="executing",
        collection_name="test_col",
        project_path=str(project_dir)
    )

    # Mock Gateway confirmation
    mock_gateway.request_confirmation.return_value = True

    # Mock internally used methods
    orchestrator._send_status = AsyncMock()
    orchestrator._plan_task = AsyncMock()
    orchestrator._queue = MagicMock(spec=TaskQueue)

    # Patch LLMClient to verify re-init
    with patch("astra.core.orchestrator.LiteLLMClient") as MockLLMClient:
        await orchestrator._handle_failure(context)

        # Verify Confirmation Request
        mock_gateway.request_confirmation.assert_called_once()

        # Verify Status Update
        orchestrator._send_status.assert_called()
        assert "Escalating to cloud model" in orchestrator._send_status.call_args_list[0][0][1]

        # Verify Config Update
        assert mock_config.llm.model == "openai/gpt-4o"

@pytest.mark.asyncio
async def test_fallback_declined(orchestrator, mock_gateway, tmp_path):
    """Test fallback flow when user declines."""
    from types import SimpleNamespace

    # Create a real directory for the mock project_path
    project_dir = tmp_path / "test_project_declined"
    project_dir.mkdir()

    task = SimpleNamespace(id="task_2", channel_id="channel_2", request="Test Task")
    context = SimpleNamespace(
        task=task,
        attempts=3,
        errors=["Error"],
        phase="executing",
        collection_name="test_col",
        project_path=str(project_dir)
    )

    # User says No
    mock_gateway.request_confirmation.return_value = False

    orchestrator._queue = MagicMock(spec=TaskQueue)
    orchestrator._send_status = AsyncMock()

    await orchestrator._handle_failure(context)

    # Verify Failure Completion
    orchestrator._queue.complete.assert_called_once()
    args = orchestrator._queue.complete.call_args
    assert args[0][0] == task
    assert args[1]['success'] is False
