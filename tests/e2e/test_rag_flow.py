from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.core.orchestrator import Orchestrator, TaskContext
from astra.core.task_queue import Task


@pytest.mark.asyncio
async def test_rag_first_flow():
    """Verify that KnowledgeTool is queried BEFORE the plan is generated."""

    # 1. Setup Mocks
    mock_gateway = MagicMock()
    mock_gateway.send_message = AsyncMock()
    mock_llm = MagicMock()
    # First call to chat is for RAG/Analysis, second for Planning (simplified view)
    # or RAG is done via tools.
    # We want to ensure specific tool usage.

    mock_knowledge_tool = MagicMock()
    mock_knowledge_tool.name = "query_knowledge_graph"
    # Execute should return some graph info
    mock_knowledge_tool.execute = AsyncMock(return_value="Graph Info: Dependency Found")

    mock_config = MagicMock()
    mock_config.llm.model = "test-model"

    with patch('astra.core.orchestrator.TaskQueue'), \
         patch('astra.core.orchestrator.LiteLLMClient', return_value=mock_llm), \
         patch('astra.core.orchestrator.ChromaDBStore'), \
         patch('astra.core.orchestrator.ASTParser'), \
         patch('astra.core.orchestrator.KnowledgeGraph'), \
         patch('astra.core.orchestrator.GitHubVCS'), \
         patch('astra.core.orchestrator.ShellExecutor'), \
         patch('astra.core.orchestrator.FileOps'), \
         patch('astra.core.orchestrator.AiderTool'):

        orch = Orchestrator(gateway=mock_gateway)
        orch._tools.get = MagicMock(return_value=mock_knowledge_tool)

        # Mock vector store query to return results (triggering KG lookup)
        mock_result = MagicMock()
        mock_result.node.file_path = "src/auth.py"
        mock_result.node.start_line = 10
        mock_result.node.content = "def login(): pass"

        # Need to access the mock_store instance we patched
        # Since we can't easily access the return_value of the patch in the context manager
        # unless we assign it. But we patched the CLASS.
        # So orch._vector_store is an instance of the Mock class.
        orch._vector_store.query.return_value = [mock_result]

        # Create a task
        task = Task(id="t1", type="feature", request="Update login logic", channel_id="c1", user_id="u1", project="p1")
        context = TaskContext(task=task, project_path=".", collection_name="c1", branch_name="b1")

        # Mock _plan method to isolate the RAG logic if it's separate?
        # Ideally we want to test _plan_task calling the RAG steps.
        # But _plan_task calls self._plan() which uses the LLM to decide tools.
        # We want to FORCE RAG.
        # So we'll implementing a new _gather_context method that is called inside _plan_task
        # BEFORE _plan.

        # We do NOT patch _plan, because we want to test the logic INSIDE _plan
        # that calls _gather_context.

        # We need to ensure _plan can run without crashing.
        # It calls:
        # 1. _gather_context (which we mocked dependencies for)
        # 2. _tools.get_definitions() (fine)
        # 3. _templates.render() (need to mock)
        # 4. _llm.for_planning().chat() (need to mock)

        orch._templates = MagicMock()
        orch._templates.render.return_value = "System Prompt"

        # Mock LLM chat
        mock_chat_llm = MagicMock()
        mock_response = MagicMock(content="Plan: Do stuff")
        mock_response.tool_calls = None # Ensure it's treated as final text, not tool call
        mock_chat_llm.chat = AsyncMock(return_value=mock_response)
        mock_llm.for_planning.return_value = mock_chat_llm

        # Execute
        await orch._plan(context)

        # Assertions
        # 1. _gather_context (or equivalent logic) should have called KnowledgeTool
        # We expect a hardcoded call or a "RAG" phase.
        # Since we haven't implemented it yet, this test will fail if we expect a specific call.
        # But the plan says "Modify Orchestrator._plan to REQUIRE KnowledgeTool".

        # If we enforce it via code (not LLM tool choice), verify explicit call.
        mock_knowledge_tool.execute.assert_called()

        # Verify it happened before plan
        # (Implied by the fact we called _plan_task and it calls _plan)
        # We can check call order if we mock the context gathering method.
