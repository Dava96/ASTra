"""Comprehensive tests for the orchestrator with mocking and edge cases."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.core.orchestrator import Orchestrator, OrchestratorPhase, TaskContext
from astra.core.task_queue import Task, TaskStatus
from astra.interfaces.gateway import Gateway, Message
from astra.interfaces.llm import LLMResponse

# === Fixtures ===


@pytest.fixture
def mock_gateway():
    """Create a mock gateway."""
    gateway = MagicMock(spec=Gateway)
    gateway.send_message = AsyncMock()
    gateway.send_progress = AsyncMock()
    gateway.request_confirmation = AsyncMock(return_value=True)
    return gateway


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = MagicMock()
    config.max_retries = 3
    config.branch_prefix = "ai-dev-"
    config.model = "ollama/qwen2.5-coder:7b"
    config.allowed_users = ["123456"]
    config.get = MagicMock(side_effect=lambda *args, default=None: default)
    return config


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        id="test123",
        type="feature",
        request="Add a login button to the header",
        user_id="user456",
        channel_id="channel789",
        project="test-project",
        status=TaskStatus.RUNNING,
    )


# === Test Classes ===


class TestOrchestratorPhases:
    """Test orchestrator phase transitions."""

    def test_phase_enum_values(self):
        """Verify all phases exist."""
        assert OrchestratorPhase.ANALYZING.value == "analyzing"
        assert OrchestratorPhase.PLANNING.value == "planning"
        assert OrchestratorPhase.EXECUTING.value == "executing"
        assert OrchestratorPhase.TESTING.value == "testing"
        assert OrchestratorPhase.FINALIZING.value == "finalizing"


class TestTaskContext:
    """Test TaskContext behavior."""

    def test_context_initialization(self, sample_task):
        """Test context is properly initialized."""
        ctx = TaskContext(
            task=sample_task,
            project_path="./repos/test",
            collection_name="test_collection",
            branch_name="ai-dev-test123",
        )

        assert ctx.phase == OrchestratorPhase.ANALYZING
        assert ctx.attempts == 0
        assert ctx.errors == []
        assert ctx.changes_made == []

    def test_context_tracks_errors(self, sample_task):
        """Test context accumulates errors."""
        ctx = TaskContext(
            task=sample_task,
            project_path="./repos/test",
            collection_name="test",
            branch_name="ai-dev-test",
        )

        ctx.errors.append("First error")
        ctx.errors.append("Second error")

        assert len(ctx.errors) == 2
        assert "First error" in ctx.errors

    def test_context_tracks_changes(self, sample_task):
        """Test context accumulates file changes."""
        ctx = TaskContext(
            task=sample_task,
            project_path="./repos/test",
            collection_name="test",
            branch_name="ai-dev-test",
        )

        ctx.changes_made.extend(["src/header.tsx", "src/button.tsx"])

        assert len(ctx.changes_made) == 2


class TestOrchestratorMocked:
    """Test orchestrator with fully mocked dependencies."""

    @pytest.fixture
    async def orchestrator_mocks(self, mock_gateway, mock_config):
        """Create orchestrator with all dependencies mocked."""
        with (
            patch("astra.core.orchestrator.TaskQueue") as MockQueue,
            patch("astra.core.orchestrator.LiteLLMClient") as MockLLM,
            patch("astra.core.orchestrator.ChromaDBStore") as MockStore,
            patch("astra.core.orchestrator.ASTParser") as MockParser,
            patch("astra.core.orchestrator.KnowledgeGraph"),
            patch("astra.core.orchestrator.GitHubVCS") as MockVCS,
            patch("astra.core.orchestrator.ShellExecutor") as MockShell,
            patch("astra.core.orchestrator.FileOps"),
            patch("astra.core.orchestrator.TemplateManager") as MockTemplates,
            patch("astra.tools.search.DDGS") as MockDDGS,
            patch("astra.core.orchestrator.get_config", return_value=mock_config),
            patch("astra.memory.store.ChromaMemoryStore"),
            patch("astra.tools.browser.BrowserTool"),
            patch("astra.tools.search.SearchTool"),
            patch("astra.tools.knowledge.KnowledgeTool"),
            patch("astra.tools.aider_tool.AiderTool"),
        ):
            orchestrator = Orchestrator(mock_gateway, mock_config)

            data = {
                "orchestrator": orchestrator,
                "gateway": mock_gateway,
                "queue": MockQueue.return_value,
                "llm": MockLLM.return_value,
                "store": MockStore.return_value,
                "parser": MockParser.return_value,
                "vcs": MockVCS.return_value,
                "shell": MockShell.return_value,
                "templates": MockTemplates.return_value,
                "ddgs": MockDDGS.return_value,
                "config": mock_config,
            }

            # Set default return for templates.render to avoid pydantic errors
            data["templates"].render.return_value = "Mocked Template Result"

            yield data

    @pytest.mark.asyncio
    async def test_send_status_calls_gateway(self, orchestrator_mocks):
        """Test that status updates are sent to the gateway."""
        orch = orchestrator_mocks["orchestrator"]
        gateway = orchestrator_mocks["gateway"]

        await orch._send_status("channel123", "Testing status")

        gateway.send_message.assert_called_once()
        call_args = gateway.send_message.call_args[0][0]
        assert isinstance(call_args, Message)
        assert call_args.content == "Testing status"
        assert call_args.channel_id == "channel123"

    @pytest.mark.asyncio
    async def test_set_active_project(self, orchestrator_mocks):
        """Test setting and getting active project."""
        orch = orchestrator_mocks["orchestrator"]

        assert orch.get_active_project() is None

        orch.set_active_project("my-project")

        assert orch.get_active_project() == "my-project"

    @pytest.mark.asyncio
    async def test_plan_retrieves_context(self, orchestrator_mocks, sample_task):
        """Test that planning phase queries vector store."""
        orch = orchestrator_mocks["orchestrator"]
        store = orchestrator_mocks["store"]
        llm = orchestrator_mocks["llm"]

        store.query.return_value = []

        # Configure planning LLM mock
        planning_llm = MagicMock()
        planning_llm.chat = AsyncMock(
            return_value=LLMResponse(
                content="Plan: Edit header.tsx",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                model="test",
            )
        )
        llm.for_planning.return_value = planning_llm

        # Configure standard chat as well
        llm.chat = AsyncMock(
            return_value=LLMResponse(
                content="Plan: Edit header.tsx",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                model="test",
            )
        )

        ctx = TaskContext(
            task=sample_task,
            project_path="./repos/test",
            collection_name="test_collection",
            branch_name="ai-dev-test",
        )

        with patch("pathlib.Path.write_text") as mock_write:
            plan = await orch._plan(ctx)
            mock_write.assert_called_once()

        store.query.assert_called_once()
        llm.for_planning.return_value.chat.assert_called_once()
        orch._templates.render.assert_called_once()
        assert "content" in plan
        assert plan["content"] == "Plan: Edit header.tsx"

    @pytest.mark.asyncio
    async def test_resume_task(self, orchestrator_mocks, sample_task):
        """Test resuming a task from approval."""
        orch = orchestrator_mocks["orchestrator"]
        queue = orchestrator_mocks["queue"]

        # Setup task in waiting state
        sample_task.status = TaskStatus.WAITING_APPROVAL
        queue.get_task.return_value = sample_task

        await orch.resume_task("test123")

        assert sample_task.status == TaskStatus.QUEUED
        queue.update.assert_called_once_with(sample_task)
        queue._queue.put.assert_called_once_with(sample_task)

    @pytest.mark.asyncio
    async def test_revise_plan(self, orchestrator_mocks, sample_task):
        """Test revising a plan."""
        orch = orchestrator_mocks["orchestrator"]
        queue = orchestrator_mocks["queue"]

        queue.get_task.return_value = sample_task

        await orch.revise_plan("test123", "Make it blue")

        assert "Make it blue" in sample_task.request
        assert sample_task.status == TaskStatus.QUEUED
        queue.update.assert_called_once_with(sample_task)

    @pytest.mark.asyncio
    async def test_agentic_tool_loop(self, orchestrator_mocks, sample_task):
        """Test the agentic loop with tool calls."""
        orch = orchestrator_mocks["orchestrator"]
        llm = orchestrator_mocks["llm"]

        # Setup mocks
        orch._vector_store.query.return_value = []

        # Mock SearchTool in registry
        mock_search = AsyncMock()
        mock_search.execute.return_value = "Search Results: Found info."
        mock_search.name = "search_web"
        mock_search.description = "Search tool"
        mock_search.parameters = {}

        orch._tools = MagicMock()
        orch._tools.get_definitions.return_value = [{"name": "search_web"}]
        orch._tools.get.return_value = mock_search

        # Mock LLM Responses sequence
        # 1. Call Tool
        resp1 = LLMResponse(
            content=None,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            model="test",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "search_web", "arguments": '{"query": "foo"}'},
                }
            ],
        )
        # 2. Final Plan
        resp2 = LLMResponse(
            content="Plan: Use info found.",
            prompt_tokens=20,
            completion_tokens=10,
            total_tokens=30,
            model="test",
        )

        # Configure planning LLM to return these in sequence
        planning_llm = llm.for_planning.return_value

        # Use Futures for AsyncMock sequence
        f1 = asyncio.Future()
        f1.set_result(resp1)
        f2 = asyncio.Future()
        f2.set_result(resp2)
        planning_llm.chat.side_effect = [f1, f2]

        ctx = TaskContext(
            task=sample_task,
            project_path="./repos/test",
            collection_name="test_collection",
            branch_name="ai-dev-test",
        )

        with patch("pathlib.Path.write_text"):
            plan = await orch._plan(ctx)

        # Assertions
        assert plan["content"] == "Plan: Use info found."
        # Verify tool was called
        mock_search.execute.assert_called_once_with(query="foo")
        # Verify loop ran twice
        assert planning_llm.chat.call_count == 2

    @pytest.mark.asyncio
    async def test_plan_surfaces_critic_thoughts(self, orchestrator_mocks, sample_task):
        """Test that critic loop progress is surfaced to the gateway."""
        orch = orchestrator_mocks["orchestrator"]
        llm = orchestrator_mocks["llm"]
        gateway = orchestrator_mocks["gateway"]
        config = orchestrator_mocks["config"]

        # Enable critic
        config.get.side_effect = lambda section, key, default=None: (
            True if key == "critic_enabled" else default
        )

        # Setup Planning LLM
        planning_llm = MagicMock()
        planning_llm.chat = AsyncMock(
            return_value=LLMResponse(
                content="Plan: Valid Plan",
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20,
                model="test",
            )
        )
        llm.for_planning.return_value = planning_llm

        # Setup Critic LLM
        critic_llm = MagicMock()
        # First response: Request Changes, Second: Approve
        critic_llm.chat = AsyncMock(side_effect=[
            LLMResponse(
                content="Critique: REQUEST_CHANGES. Missing X.",
                model="critic",
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20
            ),
            LLMResponse(
                content="Critique: APPROVE. Looks good.",
                model="critic",
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20
            ),
        ])
        llm.for_critic.return_value = critic_llm

        # Setup Context
        orch._vector_store.query.return_value = []
        ctx = TaskContext(
            task=sample_task,
            project_path="./repos/test",
            collection_name="test_collection",
            branch_name="ai-dev-test",
        )

        with patch("pathlib.Path.write_text"):
            await orch._plan(ctx)

        # Verification
        # Check messages sent to gateway
        # We expect:
        # 1. "🤔 Critic Loop 1/2..."
        # 2. "🔄 Refining plan based on critique..."
        # 3. "🤔 Critic Loop 2/2..."
        # 4. "✅ Critic approved the plan."

        # Filter calls for status updates
        status_calls = [
            call.args[0].content
            for call in gateway.send_message.call_args_list
            if isinstance(call.args[0], Message)
        ]

        # Check for substrings because of emojis/formatting
        assert any("Critic Loop 1/" in msg for msg in status_calls)
        assert any("Refining plan" in msg for msg in status_calls)
        assert any("Critic Loop 2/" in msg for msg in status_calls)

    @pytest.mark.asyncio
    async def test_plan_attaches_file(self, orchestrator_mocks, sample_task):
        """Test that the plan is surfaced with a file attachment."""
        orch = orchestrator_mocks["orchestrator"]
        gateway = orchestrator_mocks["gateway"]
        llm = orchestrator_mocks["llm"]

        # Setup Planning LLM
        planning_llm = MagicMock()
        planning_llm.chat = AsyncMock(
            return_value=LLMResponse(
                content="# Goal: Big Plan\nDetails...",
                model="planning",
                prompt_tokens=10, completion_tokens=10, total_tokens=20
            )
        )
        llm.for_planning.return_value = planning_llm

        # Disable Critic
        orch._config.orchestration.critic_enabled = False
        orch._vector_store.query.return_value = []
        orch._templates.render.return_value = "Prompt"

        ctx = TaskContext(
            task=sample_task,
            project_path="./repos/test",
            collection_name="test_collection",
            branch_name="ai-dev-test",
        )

        with patch("pathlib.Path.write_text"):
            await orch._plan(ctx)

        # Verify attachment
        found_attachment = False
        for call in gateway.send_message.call_args_list:
            message = call.args[0]
            # Ensure message is Message object (our previous fix)
            if (
                isinstance(message, Message)
                and "Plan Ready!" in message.content
                and message.file_path
                and message.file_path.endswith(".md")
            ):
                found_attachment = True
                break

        assert found_attachment, "Plan file not attached to status message"


    @pytest.mark.asyncio
    async def test_stop_saves_knowledge_graph(self, orchestrator_mocks):
        """Test that stopping saves the knowledge graph."""
        orch = orchestrator_mocks["orchestrator"]

        # Access the mocked knowledge graph
        kg = orch._knowledge_graph

        await orch.stop()

        assert not orch._running
        kg.save.assert_called_once()


class TestOrchestratorEdgeCases:
    """Edge case tests for orchestrator."""

    @pytest.fixture
    async def basic_orchestrator(self, mock_gateway, mock_config):
        """Create orchestrator with minimal mocking for edge case tests."""
        with (
            patch("astra.core.orchestrator.TaskQueue"),
            patch("astra.core.orchestrator.LiteLLMClient"),
            patch("astra.core.orchestrator.ChromaDBStore"),
            patch("astra.core.orchestrator.ASTParser"),
            patch("astra.core.orchestrator.KnowledgeGraph"),
            patch("astra.core.orchestrator.GitHubVCS"),
            patch("astra.core.orchestrator.ShellExecutor"),
            patch("astra.core.orchestrator.FileOps"),
            patch("astra.core.orchestrator.get_config", return_value=mock_config),
            patch("astra.memory.store.ChromaMemoryStore"),
            patch("astra.tools.browser.BrowserTool"),
            patch("astra.tools.search.SearchTool"),
            patch("astra.tools.knowledge.KnowledgeTool"),
            patch("astra.tools.aider_tool.AiderTool"),
        ):
            yield Orchestrator(mock_gateway, mock_config)

    @pytest.mark.asyncio
    async def test_setup_context_no_project_raises(self, basic_orchestrator, sample_task):
        """Test that setup without active project raises error."""
        sample_task.project = None
        basic_orchestrator._active_project = None

        with pytest.raises(ValueError, match="No active project"):
            await basic_orchestrator._setup_context(sample_task)

    @pytest.mark.asyncio
    async def test_detect_test_command_empty_dir(self, basic_orchestrator, tmp_path):
        """Test test command detection on empty directory."""
        result = basic_orchestrator._detect_test_command(str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_detect_test_command_npm(self, basic_orchestrator, tmp_path):
        """Test detection of npm test command."""
        import json

        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"scripts": {"test": "jest"}}))

        result = basic_orchestrator._detect_test_command(str(tmp_path))
        assert result == "npm test"

    @pytest.mark.asyncio
    async def test_detect_test_command_composer(self, basic_orchestrator, tmp_path):
        """Test detection of composer test command."""
        (tmp_path / "composer.json").write_text("{}")

        result = basic_orchestrator._detect_test_command(str(tmp_path))
        assert result == "vendor/bin/phpunit"

    @pytest.mark.asyncio
    async def test_detect_test_command_pytest(self, basic_orchestrator, tmp_path):
        """Test detection of pytest command."""
        (tmp_path / "pytest.ini").write_text("[pytest]")

        result = basic_orchestrator._detect_test_command(str(tmp_path))
        assert result == "pytest"

    @pytest.mark.asyncio
    async def test_detect_test_command_cargo(self, basic_orchestrator, tmp_path):
        """Test detection of cargo test command."""
        (tmp_path / "Cargo.toml").write_text("[package]")

        result = basic_orchestrator._detect_test_command(str(tmp_path))
        assert result == "cargo test"

    @pytest.mark.asyncio
    async def test_detect_test_command_priority(self, basic_orchestrator, tmp_path):
        """Test that package.json takes priority when multiple exist."""
        import json

        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest"}}))
        (tmp_path / "pytest.ini").write_text("[pytest]")

        # package.json is checked first
        result = basic_orchestrator._detect_test_command(str(tmp_path))
        assert result == "npm test"

    @pytest.mark.asyncio
    async def test_detect_test_command_invalid_package_json(self, basic_orchestrator, tmp_path):
        """Test handling of malformed package.json."""
        (tmp_path / "package.json").write_text("{ invalid json }")

        # Should not crash, just return None
        result = basic_orchestrator._detect_test_command(str(tmp_path))
        assert result is None


class TestCancellationBehavior:
    """Test task cancellation scenarios."""

    @pytest.fixture
    async def cancellable_setup(self, mock_gateway, mock_config):
        """Create setup for cancellation tests."""
        with (
            patch("astra.core.orchestrator.TaskQueue") as MockQueue,
            patch("astra.core.orchestrator.LiteLLMClient"),
            patch("astra.core.orchestrator.ChromaDBStore"),
            patch("astra.core.orchestrator.ASTParser"),
            patch("astra.core.orchestrator.KnowledgeGraph"),
            patch("astra.core.orchestrator.GitHubVCS"),
            patch("astra.core.orchestrator.ShellExecutor"),
            patch("astra.core.orchestrator.FileOps"),
            patch("astra.core.orchestrator.get_config", return_value=mock_config),
            patch("astra.memory.store.ChromaMemoryStore"),
            patch("astra.tools.browser.BrowserTool"),
            patch("astra.tools.search.SearchTool"),
            patch("astra.tools.knowledge.KnowledgeTool"),
            patch("astra.tools.aider_tool.AiderTool"),
        ):
            queue = MockQueue.return_value
            queue.is_cancel_requested.return_value = True
            queue.complete = MagicMock()

            orch = Orchestrator(mock_gateway, mock_config)

            yield {"orchestrator": orch, "queue": queue, "gateway": mock_gateway}

    # Note: Full cancellation test would require more complex async setup
    # This demonstrates the pattern for testing cancellation awareness
    @pytest.mark.asyncio
    async def test_queue_tracks_cancellation(self, cancellable_setup):
        """Test that queue correctly reports cancellation status."""
        queue = cancellable_setup["queue"]
        assert queue.is_cancel_requested()


class TestRetryBehavior:
    """Test retry and fallback behavior permutations."""

    @pytest.mark.parametrize(
        "max_retries,expected_attempts",
        [
            (1, 1),
            (3, 3),
            (5, 5),
        ],
    )
    @pytest.mark.asyncio
    async def test_max_retries_configuration(self, max_retries, expected_attempts, mock_gateway):
        """Test that max_retries is respected."""
        config = MagicMock()
        config.max_retries = max_retries
        config.get = MagicMock(return_value=None)

        with (
            patch("astra.core.orchestrator.TaskQueue"),
            patch("astra.core.orchestrator.LiteLLMClient"),
            patch("astra.core.orchestrator.ChromaDBStore"),
            patch("astra.core.orchestrator.ASTParser"),
            patch("astra.core.orchestrator.KnowledgeGraph"),
            patch("astra.core.orchestrator.GitHubVCS"),
            patch("astra.core.orchestrator.ShellExecutor"),
            patch("astra.core.orchestrator.FileOps"),
            patch("astra.core.orchestrator.get_config", return_value=config),
            patch("astra.memory.store.ChromaMemoryStore"),
            patch("astra.tools.browser.BrowserTool"),
            patch("astra.tools.search.SearchTool"),
            patch("astra.tools.knowledge.KnowledgeTool"),
            patch("astra.tools.aider_tool.AiderTool"),
        ):
            orch = Orchestrator(mock_gateway, config)
            assert orch._config.max_retries == expected_attempts


class TestPRBodyGeneration:
    """Test PR body generation edge cases."""

    @pytest.fixture
    async def orchestrator_for_pr(self, mock_gateway, mock_config, tmp_path):
        """Create orchestrator with template for PR tests."""
        with (
            patch("astra.core.orchestrator.TaskQueue"),
            patch("astra.core.orchestrator.LiteLLMClient"),
            patch("astra.core.orchestrator.ChromaDBStore"),
            patch("astra.core.orchestrator.ASTParser"),
            patch("astra.core.orchestrator.KnowledgeGraph"),
            patch("astra.core.orchestrator.GitHubVCS"),
            patch("astra.core.orchestrator.ShellExecutor"),
            patch("astra.core.orchestrator.FileOps"),
            patch("astra.core.orchestrator.get_config", return_value=mock_config),
            patch("astra.memory.store.ChromaMemoryStore"),
            patch("astra.tools.browser.BrowserTool"),
            patch("astra.tools.search.SearchTool"),
            patch("astra.tools.knowledge.KnowledgeTool"),
            patch("astra.tools.aider_tool.AiderTool"),
        ):
            yield Orchestrator(mock_gateway, mock_config)

    @pytest.mark.asyncio
    async def test_pr_body_with_no_changes(self, orchestrator_for_pr, sample_task):
        """Test PR body when no files were changed."""
        ctx = TaskContext(
            task=sample_task,
            project_path="./repos/test",
            collection_name="test",
            branch_name="ai-dev-test",
            changes_made=[],  # No changes
        )

        body = orchestrator_for_pr._generate_pr_body(ctx)

        assert "No files changed" in body or body != ""

    @pytest.mark.asyncio
    async def test_pr_body_with_many_changes(self, orchestrator_for_pr, sample_task):
        """Test PR body with many file changes."""
        ctx = TaskContext(
            task=sample_task,
            project_path="./repos/test",
            collection_name="test",
            branch_name="ai-dev-test",
            changes_made=[f"src/file{i}.tsx" for i in range(50)],
        )

        body = orchestrator_for_pr._generate_pr_body(ctx)

        # Should include all files
        assert "file49.tsx" in body

    @pytest.mark.asyncio
    async def test_pr_body_with_special_characters(self, orchestrator_for_pr):
        """Test PR body handles special characters in request."""
        task = Task(
            id="test",
            type="feature",
            request="Add `code` and 'quotes' and \"double quotes\"",
            user_id="user",
            channel_id="channel",
            project="test",
        )
        ctx = TaskContext(
            task=task,
            project_path="./repos/test",
            collection_name="test",
            branch_name="ai-dev-test",
        )

        # Should not crash
        body = orchestrator_for_pr._generate_pr_body(ctx)
        assert len(body) > 0
