"""Integration tests for the ASTra core orchestrator."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.core.orchestrator import Orchestrator
from astra.core.task_queue import Task, TaskStatus


@pytest.mark.asyncio
class TestCoreIntegration:
    """Integration tests for the Orchestrator loop."""

    @pytest.fixture
    def mock_gateway(self):
        gateway = MagicMock()
        gateway.send_message = AsyncMock()
        return gateway

    @pytest.fixture
    async def orchestrator(self, mock_gateway):
        with patch("astra.core.orchestrator.LiteLLMClient"), \
             patch("astra.core.orchestrator.ChromaDBStore"), \
             patch("astra.core.orchestrator.KnowledgeGraph"), \
             patch("astra.core.orchestrator.GitHubVCS"), \
             patch("astra.core.orchestrator.AiderTool"), \
             patch("astra.core.orchestrator.TemplateManager"), \
             patch("astra.core.orchestrator.ShellExecutor"):
            orch = Orchestrator(gateway=mock_gateway)
            orch._active_project = "test-project" # Set dummy project

            # Use in-memory task queue for testing
            orch._queue = MagicMock()

            # Helper to allow processing a task through side_effect
            def get_next():
                return None

            orch._queue.get_next.side_effect = get_next
            orch._queue.update.side_effect = lambda t: None

            def mock_complete(t, **kwargs):
                t.status = TaskStatus.SUCCESS if kwargs.get('success') else TaskStatus.FAILED
                if 'error' in kwargs:
                    t.error = kwargs['error']
            orch._queue.complete.side_effect = mock_complete
            orch._queue.is_cancel_requested.return_value = False

            # Mock shell to return success
            orch._shell = AsyncMock()
            orch._shell.run_async.return_value = MagicMock(returncode=0, stdout="", stderr="")

            return orch

    async def test_orchestrator_full_loop_to_wait_approval(self, orchestrator, mock_gateway):
        """Test that a task goes from QUEUED to WAITING_APPROVAL after planning."""
        task = Task(id="test-task", type="feature", request="implement hello world", user_id="user1", channel_id="chan1")

        # Controlled task delivery
        delivery_state = {"delivered": False}
        def get_next():
            if not delivery_state["delivered"]:
                delivery_state["delivered"] = True
                return task
            return None

        orchestrator._queue.get_next.side_effect = get_next

        # Mock planning
        mock_plan = {
            "content": "# Plan\nDo stuff",
            "filename": "plan.md",
            "goal": "implement hello world",
            "tokens": 100
        }

        from astra.core.orchestrator import TaskContext
        mock_context = TaskContext(
            task=task,
            project_path="./repos/test-project",
            collection_name="test-project-db",
            branch_name="astra/test-task"
        )

        with patch.object(orchestrator, "_setup_context", new_callable=AsyncMock, return_value=mock_context), \
             patch.object(orchestrator, "_plan", new_callable=AsyncMock, return_value=mock_plan):

            # Start orchestrator
            running_task = asyncio.create_task(orchestrator.start())

            # Poll for status change with timeout
            start_poll = time.time()
            while task.status == TaskStatus.QUEUED and time.time() - start_poll < 5.0:
                await asyncio.sleep(0.1)

            if task.status == TaskStatus.FAILED:
                pytest.fail(f"Task failed unexpectedly: {task.error}")

            await orchestrator.stop()
            try:
                await asyncio.wait_for(running_task, timeout=1.0)
            except (TimeoutError, asyncio.CancelledError):
                running_task.cancel()

            # Verify status transitions
            assert task.status == TaskStatus.WAITING_APPROVAL

            # Verify gateway notifications
            calls = mock_gateway.send_message.call_args_list
            messages = [c.args[0].content for c in calls]
            assert any("🔍 Analyzing request" in m for m in messages)
            assert any("📋 **Plan Ready!**" in m for m in messages)

    async def test_orchestrator_resume_to_success(self, orchestrator, mock_gateway):
        """Test resuming a task from WAITING_APPROVAL to SUCCESS."""
        task = Task(
            id="test-task",
            type="feature",
            request="implement hello world",
            user_id="user1",
            channel_id="chan1",
            status=TaskStatus.WAITING_APPROVAL,
            result={"implementation_plan": {"content": "plan", "filename": "p.md", "goal": "g"}}
        )

        delivery_state = {"delivered": False}
        def get_next():
            if not delivery_state["delivered"]:
                delivery_state["delivered"] = True
                return task
            return None

        orchestrator._queue.get_next.side_effect = get_next

        from astra.core.orchestrator import TaskContext
        mock_context = TaskContext(
            task=task,
            project_path="./repos/test-project",
            collection_name="test-project-db",
            branch_name="astra/test-task"
        )

        with patch.object(orchestrator, "_setup_context", new_callable=AsyncMock, return_value=mock_context), \
             patch.object(orchestrator, "_execute", new_callable=AsyncMock), \
             patch.object(orchestrator, "_test", new_callable=AsyncMock, return_value=True), \
             patch.object(orchestrator, "_finalize", new_callable=AsyncMock, return_value={"pr_url": "http://pr"}):

            running_task = asyncio.create_task(orchestrator.start())

            # Poll for SUCCESS status
            start_poll = time.time()
            while task.status != TaskStatus.SUCCESS and task.status != TaskStatus.FAILED and time.time() - start_poll < 5.0:
                await asyncio.sleep(0.1)

            if task.status == TaskStatus.FAILED:
                pytest.fail(f"Task failed unexpectedly: {task.error}")

            await orchestrator.stop()
            try:
                await asyncio.wait_for(running_task, timeout=1.0)
            except (TimeoutError, asyncio.CancelledError):
                running_task.cancel()

            assert task.status == TaskStatus.SUCCESS
            assert orchestrator._queue.complete.called

            calls = mock_gateway.send_message.call_args_list
            messages = [c.args[0].content for c in calls]
            assert any("🧪 Running tests" in m for m in messages)
            assert any("✅ Task complete!" in m for m in messages)
