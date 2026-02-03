from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.handlers.command_handlers import CommandHandler
from astra.interfaces.gateway import Command


@pytest.fixture
def mock_deps():
    gateway = MagicMock()
    gateway.send_followup = AsyncMock()

    orchestrator = MagicMock()
    orchestrator.get_active_project.return_value = "user/repo"
    orchestrator.resume_task = AsyncMock()
    orchestrator.revise_plan = AsyncMock()
    orchestrator.set_active_project = MagicMock()

    queue = MagicMock()
    queue.add.return_value = MagicMock(id="task-1")
    queue.get_position.return_value = 1
    queue.get_queue_status.return_value = {
        "queued": 0, "current": None, "recent": []
    }

    config = MagicMock()
    config.get.side_effect = lambda cat, key, default=None: default
    config.llm.model = "gpt-4"
    config.orchestration.allowed_users = []

    return gateway, orchestrator, queue, config

@pytest.fixture
def handler(mock_deps):
    return CommandHandler(*mock_deps)

@pytest.fixture
def mock_cmd():
    cmd = MagicMock(spec=Command)
    cmd.raw_interaction = MagicMock()
    cmd.user_id = "user1"
    cmd.channel_id = "channel1"
    cmd.args = {}
    return cmd

@pytest.mark.asyncio
async def test_handle_feature(handler, mock_deps, mock_cmd):
    gateway, orchestrator, queue, _ = mock_deps
    mock_cmd.args = {"request": "New Feature"}

    await handler.handle_feature(mock_cmd)

    queue.add.assert_called_once()
    gateway.send_followup.assert_called()
    assert "Task queued" in gateway.send_followup.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_checkout_success(handler, mock_deps, mock_cmd):
    gateway, orchestrator, _, _ = mock_deps
    mock_cmd.args = {"request": "http://github.com/user/repo.git"}

    with patch("astra.handlers.project_handlers.Safeguard") as MockSafe, \
         patch("astra.handlers.project_handlers.GitHubVCS") as MockVCS, \
         patch("astra.handlers.project_handlers.asyncio.create_task") as MockTask:

        # Setup mocks
        orchestrator._vector_store.get_collection_stats.return_value = {"count": 0}
        MockSafe.return_value.check_repo_size.return_value = (True, "")
        MockSafe.return_value.check_system_resources.return_value = (True, "")

        vcs = MockVCS.return_value
        vcs.clone = AsyncMock(return_value=MagicMock(success=True, repo_path="repo"))
        vcs.get_current_branch = AsyncMock(return_value="main")

        await handler.handle_checkout(mock_cmd)

        vcs.clone.assert_called()
        orchestrator.set_active_project.assert_called_with("repo")
        MockTask.assert_called()
        gateway.send_followup.assert_called()
        assert "Background indexing started" in gateway.send_followup.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_status(handler, mock_deps, mock_cmd):
    gateway, _, queue, _ = mock_deps
    queue.get_queue_status.return_value = {
        "queued": 1,
        "current": {"request": "Current Task"},
        "recent": [{"id": "1", "status": "success", "request": "Old Task"}]
    }

    await handler.handle_status(mock_cmd)

    gateway.send_followup.assert_called()
    msg = gateway.send_followup.call_args[0][1]
    assert "Current Task" in msg
    assert "Old Task" in msg

@pytest.mark.asyncio
async def test_handle_cancel(handler, mock_deps, mock_cmd):
    gateway, _, queue, _ = mock_deps
    queue.cancel_current.return_value = True

    await handler.handle_cancel(mock_cmd)

    assert "Cancellation requested" in gateway.send_followup.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_approve(handler, mock_deps, mock_cmd):
    gateway, orchestrator, _, _ = mock_deps
    mock_cmd.args = {"task_id": "123"}

    await handler.handle_approve(mock_cmd)

    orchestrator.resume_task.assert_called_with("123")
    assert "approved" in gateway.send_followup.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_screenshot(handler, mock_deps, mock_cmd):
    gateway, _, _, _ = mock_deps
    mock_cmd.args = {"url": "http://google.com"}

    # Mock discord module to avoid File/Embed errors
    with patch("astra.handlers.system_handlers.BrowserTool") as MockBrowser, \
         patch.dict("sys.modules", {"discord": MagicMock()}):

        browser = AsyncMock()
        MockBrowser.return_value.__aenter__.return_value = browser

        # Mock result
        result = MagicMock()
        result.path = "shot.png"
        result.title = "Google"
        result.load_time_ms = 100
        browser.screenshot.return_value = result

        await handler.handle_screenshot(mock_cmd)

        # Verify browser call
        browser.screenshot.assert_called_with("http://google.com", full_page=False)

        # Verify gateway call (should be called twice: start + finish)
        assert gateway.send_followup.call_count >= 2

        # Get the LAST call which should contain the embed/file
        call_args = gateway.send_followup.call_args
        # Check kwargs
        assert "embed" in call_args.kwargs
        assert "file" in call_args.kwargs

@pytest.mark.asyncio
async def test_handle_health(handler, mock_deps, mock_cmd):
    gateway, _, _, _ = mock_deps

    # Monitor is pre-instantiated in SystemHandlers.__init__, so patching the class is too late.
    # We must replace the instance directly.
    mock_monitor = MagicMock()
    mock_monitor.run_all_checks.return_value = {"cpu": (True, "OK")}
    mock_monitor.get_alerts.return_value = ["High CPU"]

    handler.system.monitor = mock_monitor

    await handler.handle_health(mock_cmd)

    assert gateway.send_followup.called
    msg = gateway.send_followup.call_args[0][1]
    assert "Cpu**: OK" in msg
    assert "High CPU" in msg

@pytest.mark.asyncio
async def test_handle_revise(handler, mock_deps, mock_cmd):
    gateway, orchestrator, _, _ = mock_deps
    mock_cmd.args = {"task_id": "1", "feedback": "better"}

    await handler.handle_revise(mock_cmd)

    orchestrator.revise_plan.assert_called_with("1", "better")
    assert "queued for revision" in gateway.send_followup.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_fix(handler, mock_deps, mock_cmd):
    gateway, _, queue, _ = mock_deps
    mock_cmd.args = {"request": "Fix bug"}

    await handler.handle_fix(mock_cmd)

    queue.add.assert_called()
    assert "[BUG FIX]" in queue.add.call_args.kwargs["request"]
    assert "Bug fix queued" in gateway.send_followup.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_quick(handler, mock_deps, mock_cmd):
    gateway, _, queue, _ = mock_deps
    mock_cmd.args = {"file": "main.py", "change": "typo"}

    await handler.handle_quick(mock_cmd)

    queue.add.assert_called()
    assert "[QUICK EDIT]" in queue.add.call_args.kwargs["request"]
    assert "Quick edit queued" in gateway.send_followup.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_history(handler, mock_deps, mock_cmd):
    gateway, _, queue, _ = mock_deps

    # Create valid status
    queue.get_queue_status.return_value = {
        "recent": [{"id": "1", "status": "success", "request": "req"}]
    }

    await handler.handle_history(mock_cmd)

    gateway.send_followup.assert_called()
    assert "Task History" in gateway.send_followup.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_config(handler, mock_deps, mock_cmd):
    gateway, _, _, config = mock_deps
    mock_cmd.args = {"action": "list"}

    await handler.handle_config(mock_cmd)

    gateway.send_followup.assert_called()
    assert "Current Configuration" in gateway.send_followup.call_args[0][1]

@pytest.mark.asyncio
async def test_handle_model(handler, mock_deps, mock_cmd):
    gateway, _, _, config = mock_deps
    mock_cmd.args = {"model": "gpt-5"}

    await handler.handle_model(mock_cmd)

    assert "model changed" in gateway.send_followup.call_args[0][1].lower()

@pytest.mark.asyncio
async def test_handle_auth(handler, mock_deps, mock_cmd):
    gateway, _, _, config = mock_deps
    config.orchestration.allowed_users = ["123"]

    # List
    mock_cmd.args = {"action": "list"}
    await handler.handle_auth(mock_cmd)
    assert "**Authorized Users**" in gateway.send_followup.call_args[0][1]

    # Add
    mock_cmd.args = {"action": "add", "user_id": "456"}
    gateway.add_authorized_user.return_value = True
    await handler.handle_auth(mock_cmd)
    gateway.add_authorized_user.assert_called_with("456")

    # Remove
    mock_cmd.args = {"action": "remove", "user_id": "456"}
    gateway.remove_authorized_user.return_value = True
    await handler.handle_auth(mock_cmd)
    gateway.remove_authorized_user.assert_called_with("456")

@pytest.mark.asyncio
async def test_handle_tools(handler, mock_deps, mock_cmd):
    gateway, orchestrator, _, _ = mock_deps

    # Mock tools
    tool = MagicMock()
    tool.name = "test_tool"
    tool.description = "desc"
    orchestrator._tools.list_tools.return_value = [tool]

    await handler.handle_tools(mock_cmd)

    msg = gateway.send_followup.call_args[0][1]
    assert "test_tool" in msg
    assert "desc" in msg

@pytest.mark.asyncio
async def test_handle_last(handler, mock_deps, mock_cmd):
    gateway, _, queue, _ = mock_deps

    # Success case
    mock_result = MagicMock()
    mock_result.status.value = "success"
    mock_result.request = "req"
    mock_result.result = {"pr_url": "http://pr"}
    mock_result.error = None
    queue.get_last_result.return_value = mock_result

    await handler.handle_last(mock_cmd)
    msg = gateway.send_followup.call_args[0][1]
    assert "Success" in msg
    assert "http://pr" in msg

    # Failure case
    mock_result.status.value = "failed"
    mock_result.error = "Boom"
    queue.get_last_result.return_value = mock_result

    await handler.handle_last(mock_cmd)
    msg = gateway.send_followup.call_args[0][1]
    assert "Failed" in msg
    assert "Boom" in msg
