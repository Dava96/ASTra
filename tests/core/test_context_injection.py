"""Tests for context and plan injection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.core.orchestrator import Orchestrator, TaskContext
from astra.core.task_queue import Task


class TestContextInjection:
    @pytest.fixture
    def mocks(self):
        mock_gateway = MagicMock()
        mock_config = MagicMock()
        mock_config.model = "gpt-4"

        with patch('astra.core.orchestrator.TaskQueue'), \
             patch('astra.core.orchestrator.LiteLLMClient'), \
             patch('astra.core.orchestrator.ChromaDBStore'), \
             patch('astra.core.orchestrator.ASTParser'), \
             patch('astra.core.orchestrator.KnowledgeGraph'), \
             patch('astra.core.orchestrator.GitHubVCS'), \
             patch('astra.core.orchestrator.ShellExecutor'), \
             patch('astra.core.orchestrator.FileOps'), \
             patch('astra.core.orchestrator.AiderTool') as MockAider, \
             patch('astra.core.orchestrator.TemplateManager'), \
             patch('astra.core.orchestrator.ToolRegistry'):

            orchestrator = Orchestrator(mock_gateway, mock_config)

            yield {
                'orchestrator': orchestrator,
                'aider': MockAider.return_value
            }

    @pytest.mark.asyncio
    async def test_plan_context_injection(self, mocks):
        """Verify approved plan is injected into Aider instruction."""
        orch = mocks['orchestrator']
        mock_aider = orch._aider # Actually accessing the instance on orch

        # Configure Aider Mock
        mock_aider.run_async = AsyncMock()
        mock_aider.run_async.return_value.success = True
        mock_aider.run_async.return_value.files_modified = []

        # Mock task and context
        task = Task(
            id="t1",
            request="Implement feature X",
            user_id="u1",
            channel_id="c1",
            type="feature"
        )
        ctx = TaskContext(
            task=task,
            project_path="./repos/test",
            collection_name="col",
            branch_name="branch"
        )

        # Plan data
        plan = {"content": "Step 1: Do A\nStep 2: Do B", "filename": "plan.md"}

        # Execute
        await orch._execute(ctx, plan)

        # Verify call args
        call_args = mock_aider.run_async.call_args
        message = call_args.kwargs['message']

        # Assertions
        assert "Implement feature X" in message
        assert "## Approved Implementation Plan" in message
        assert "Step 1: Do A" in message
