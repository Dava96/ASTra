
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.core.orchestrator import Orchestrator, TaskContext
from astra.core.task_queue import Task, TaskStatus


@pytest.fixture
def mock_gateway():
    gateway = AsyncMock()
    gateway.request_confirmation.return_value = True
    return gateway

@pytest.fixture
def orchestrator(mock_gateway, tmp_path):
    # Flexible MagicMock for config
    cfg = MagicMock()
    cfg.max_retries = 3
    cfg.llm.model = "qwen"
    cfg.llm.planning_model = "gpt-4"
    cfg.orchestration.fallback_model = "gpt-4"
    cfg.git.branch_prefix = "astra-"

    def mock_get(k1, k2, default=None):
        if k2 == "max_retries": return 3
        if k2 == "repos_dir": return str(tmp_path / "repos")
        if k2 == "branch_prefix": return "astra-"
        if k2 == "fallback_to_cloud": return False
        return default
    cfg.get.side_effect = mock_get

    with patch("astra.core.orchestrator.TaskQueue") as MockQueue, \
         patch("astra.core.orchestrator.LiteLLMClient"), \
         patch("astra.core.orchestrator.ChromaDBStore"), \
         patch("astra.core.orchestrator.ASTParser"), \
         patch("astra.core.orchestrator.KnowledgeGraph"), \
         patch("astra.core.orchestrator.GitHubVCS"), \
         patch("astra.core.orchestrator.ShellExecutor"), \
         patch("astra.core.orchestrator.FileOps"), \
         patch("astra.core.orchestrator.AiderTool"), \
         patch("astra.core.orchestrator.TemplateManager"), \
         patch("astra.core.orchestrator.get_config", return_value=cfg):

        orch = Orchestrator(gateway=mock_gateway)
        orch._running = True

        # CRITICAL: Mock is_cancel_requested to return False
        orch._queue.is_cancel_requested.return_value = False

        def mock_complete(task, success, result=None, error=None):
            task.status = TaskStatus.SUCCESS if success else TaskStatus.FAILED
            task.result = result
            task.error = error
        orch._queue.complete.side_effect = mock_complete

        return orch

def test_orchestrator_init(orchestrator):
    assert orchestrator._gateway is not None
    assert orchestrator._running is True

@pytest.mark.asyncio
async def test_orchestrator_start_stop(orchestrator):
    orchestrator._running = False
    orchestrator._queue.get_next.side_effect = [None]
    start_task = asyncio.create_task(orchestrator.start())
    await asyncio.sleep(0.1)
    await orchestrator.stop()
    await start_task
    assert orchestrator._running is False

@pytest.mark.asyncio
async def test_orchestrator_process_task_success(orchestrator, tmp_path):
    task = Task(id="t1", type="feature", request="test", user_id="u1", channel_id="c1")
    p_path = str(tmp_path / "p1")
    os.makedirs(p_path, exist_ok=True)

    orchestrator._setup_context = AsyncMock(return_value=TaskContext(
        task=task,
        project_path=p_path,
        collection_name="p1",
        branch_name="b1"
    ))
    orchestrator._plan = AsyncMock(return_value={"filename": "p.md", "goal": "g"})
    orchestrator._execute = AsyncMock()
    orchestrator._test = AsyncMock(return_value=True)
    orchestrator._finalize = AsyncMock(return_value={"pr_url": "http://pr"})

    await orchestrator._process_task(task)
    assert task.status == TaskStatus.WAITING_APPROVAL

    task.status = TaskStatus.RUNNING
    orchestrator._setup_context.reset_mock()
    orchestrator._setup_context.return_value = TaskContext(
        task=task, project_path=p_path, collection_name="p1", branch_name="b1"
    )

    await orchestrator._process_task(task)
    assert task.status == TaskStatus.SUCCESS

@pytest.mark.asyncio
async def test_orchestrator_setup_context_real(orchestrator, tmp_path):
    task = Task(id="t2", type="feature", request="test", user_id="u1", channel_id="c1", project="p1")

    with patch("astra.core.architecture.ArchitectureGenerator") as MockArch:
        mock_gen = MockArch.return_value
        mock_gen.generate_if_missing = AsyncMock()

        ctx = await orchestrator._setup_context(task)
        assert "repos" in ctx.project_path

@pytest.mark.asyncio
async def test_orchestrator_handle_failure(orchestrator, tmp_path):
    task = Task(id="t3", type="feature", request="test", user_id="u1", channel_id="c1")
    p_path = str(tmp_path / "p3")
    os.makedirs(p_path, exist_ok=True)
    ctx = TaskContext(task=task, project_path=p_path, collection_name="c", branch_name="b")
    ctx.errors = ["err1"]

    # Enable fallback
    orchestrator._config.get.side_effect = lambda k1, k2, default=None: True if k2 == "fallback_to_cloud" else default
    orchestrator._plan = AsyncMock(return_value={"goal": "fail-retry"})

    await orchestrator._handle_failure(ctx)
    assert ctx.attempts == 0
    orchestrator._plan.assert_called()

def test_orchestrator_project_utils(orchestrator):
    orchestrator.set_active_project("proj")
    assert orchestrator.get_active_project() == "proj"

@pytest.mark.asyncio
async def test_orchestrator_plan_method(orchestrator, tmp_path):
    task = Task(id="t4", type="feature", request="test", user_id="u1", channel_id="c1")
    p_path = str(tmp_path / "p4")
    os.makedirs(p_path, exist_ok=True)
    ctx = TaskContext(task=task, project_path=p_path, collection_name="c", branch_name="b")

    mock_res_tool = MagicMock()
    mock_res_tool.tool_calls = [{"id": "1", "type": "function", "function": {"name": "search", "arguments": "{}"}}]
    mock_res_tool.content = ""

    mock_res_plan = MagicMock()
    mock_res_plan.tool_calls = None
    mock_res_plan.content = "# test\n\nGoal: test goal\n\nSteps: []"
    mock_res_plan.total_tokens = 100

    orchestrator._llm.chat = AsyncMock(side_effect=[mock_res_tool, mock_res_plan])
    orchestrator._llm.for_planning = MagicMock(return_value=orchestrator._llm)

    orchestrator._gather_context = AsyncMock(return_value="context")
    orchestrator._tools.execute = AsyncMock(return_value={"result": "found"})

    plan = await orchestrator._plan(ctx)
    assert plan["goal"] == "test"
    assert os.path.exists(os.path.join(p_path, f"implementation_plan_{task.id}.md"))
