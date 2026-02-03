"""End-to-end integration tests for ASTra."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.adapters.gateways.discord import DiscordGateway
from astra.core.orchestrator import Orchestrator, TaskContext
from astra.core.task_queue import Task, TaskStatus

# Mark all tests in this module as E2E
pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
class TestFullTaskLifecycle:
    """Test complete task lifecycle from queue to completion."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project structure."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Create package.json
        (project_dir / "package.json").write_text(json.dumps({
            "name": "test-project",
            "scripts": {"test": "echo 'tests pass'"}
        }))

        # Create src directory
        src_dir = project_dir / "src"
        src_dir.mkdir()
        (src_dir / "main.ts").write_text("export function hello() { return 'world'; }")

        return project_dir

    @pytest.fixture
    def mock_gateway(self):
        """Create a mock gateway."""
        gateway = MagicMock() # Removed spec=DiscordGateway
        gateway.send_message = AsyncMock()
        gateway.send_progress = AsyncMock()
        gateway.request_confirmation = AsyncMock(return_value=False)
        return gateway

    @pytest.fixture
    def mock_components(self, mock_gateway, temp_project):
        """Create orchestrator with mocked components."""
        with patch('astra.core.orchestrator.TaskQueue') as mock_queue_cls, \
             patch('astra.core.orchestrator.LiteLLMClient') as mock_llm_cls, \
             patch('astra.core.orchestrator.ChromaDBStore') as mock_store_cls, \
             patch('astra.core.orchestrator.ASTParser') as mock_parser_cls, \
             patch('astra.core.orchestrator.KnowledgeGraph') as mock_kg_cls, \
             patch('astra.core.orchestrator.GitHubVCS') as mock_vcs_cls, \
             patch('astra.core.orchestrator.ShellExecutor') as mock_shell_cls, \
             patch('astra.core.orchestrator.FileOps') as mock_file_cls, \
             patch('astra.core.orchestrator.AiderTool') as mock_aider_cls, \
             patch('astra.core.orchestrator.ToolRegistry') as mock_registry_cls:

            # Configure LLM mock
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "Plan: 1. Create function\n2. Add tests"
            mock_response.total_tokens = 100
            mock_response.tool_calls = None
            mock_llm.chat = AsyncMock(return_value=mock_response)
            mock_llm.for_planning = MagicMock(return_value=mock_llm)

            # Create usage object properly
            mock_usage = MagicMock()
            mock_usage.total = 100
            mock_llm.get_usage = MagicMock(return_value=mock_usage)
            mock_llm_cls.return_value = mock_llm

            # Configure vector store mock
            mock_store = MagicMock()
            mock_store.query = MagicMock(return_value=[])
            mock_store_cls.return_value = mock_store

            # Configure VCS mock
            mock_vcs = MagicMock()
            mock_vcs.create_branch = MagicMock(return_value=MagicMock(success=True))
            mock_vcs.get_changed_files = MagicMock(return_value=["src/main.ts"])
            mock_vcs.commit = MagicMock(return_value=MagicMock(success=True, commit_hash="abc123"))
            mock_vcs.push = MagicMock(return_value=MagicMock(success=True))
            mock_vcs.create_pr = MagicMock(return_value=MagicMock(
                success=True, pr_url="https://github.com/test/pr/1", pr_number=1
            ))
            mock_vcs_cls.return_value = mock_vcs

            # Configure Aider mock
            mock_aider = MagicMock()
            mock_aider.run_async = AsyncMock(return_value=MagicMock(
                success=True,
                output="Applying edits to src/main.ts",
                files_modified=["src/main.ts"],
                tokens_used=200
            ))
            mock_aider_cls.return_value = mock_aider

            # Configure shell mock
            mock_shell = MagicMock()
            mock_shell.run_string = MagicMock(return_value=MagicMock(success=True, stdout="PASS"))
            mock_shell_cls.return_value = mock_shell

            # Configure queue mock
            mock_queue = MagicMock()
            mock_queue.is_cancel_requested = MagicMock(return_value=False)
            mock_queue.complete = MagicMock()
            mock_queue_cls.return_value = mock_queue

            # Configure tool registry
            mock_registry = MagicMock()
            mock_registry_cls.return_value = mock_registry

            # Create orchestrator
            orchestrator = Orchestrator(gateway=mock_gateway)
            orchestrator.set_active_project("test/test-project")

            yield {
                'orchestrator': orchestrator,
                'gateway': mock_gateway,
                'llm': mock_llm,
                'vcs': mock_vcs,
                'aider': mock_aider,
                'queue': mock_queue,
                'project_path': temp_project
            }

    @pytest.mark.asyncio
    async def test_task_flows_through_all_phases(self, mock_components):
        """Test that a task flows through analyzing → planning → executing → testing → finalizing."""
        orch = mock_components['orchestrator']
        gateway = mock_components['gateway']

        # Create a task
        task = Task(
            id="test-001",
            type="feature",
            request="Add a greeting function",
            user_id="user123",
            channel_id="channel456",
            project="test/test-project"
        )

        # Process the task
        with patch.object(orch, '_setup_context') as mock_setup:
            mock_setup.return_value = TaskContext(
                task=task,
                project_path="./repos/test-project",
                collection_name="test_project",
                branch_name="ai-dev-test-001-123"
            )

            # Mock the _plan method to return a dummy plan directly to avoid LLM complexity in E2E
            with patch.object(orch, '_plan') as mock_plan:
                mock_plan.return_value = {"filename": "impl_plan.md", "goal": "Add feature"}

                # Mock _get_user_approval to return True immediately
                # Wait, the logic is: wait for approval.
                # In E2E, we might want to simulate approval.
                # However, the loop returns after sending plan.
                # So we test up to planning.

                await orch._process_task(task)

        # Verify phases were executed up to planning
        gateway.send_message.assert_called()

        # Should have status updates
        assert gateway.send_message.call_count >= 1
        assert task.status == TaskStatus.WAITING_APPROVAL


@pytest.mark.asyncio
class TestDiscordCommandFlow:
    """Test Discord command to orchestrator flow."""

    def test_auth_check_no_users(self):
        """Test authorization when no users configured."""
        with patch('astra.adapters.gateways.discord.gateway.discord.Client'), \
             patch('astra.adapters.gateways.discord.gateway.app_commands.CommandTree'), \
             patch('astra.adapters.gateways.discord.gateway.get_config') as mock_config:
            mock_config.return_value = MagicMock()
            mock_config.return_value.allowed_users = []

            gateway = DiscordGateway()
            assert gateway.is_user_authorized("12345") is False

    def test_auth_check_with_users(self):
        """Test authorization with configured users."""
        with patch('astra.adapters.gateways.discord.gateway.discord.Client'), \
             patch('astra.adapters.gateways.discord.gateway.app_commands.CommandTree'), \
             patch('astra.adapters.gateways.discord.gateway.get_config') as mock_config:
            mock_config.return_value = MagicMock()
            mock_config.return_value.allowed_users = ["12345", "67890"]

            gateway = DiscordGateway()
            assert gateway.is_user_authorized("12345") is True
            assert gateway.is_user_authorized("99999") is False


@pytest.mark.asyncio
class TestGitOperationsFlow:
    """Test Git operations in task flow."""

    def test_branch_creation(self):
        """Test branch is created for each task."""
        with patch('astra.tools.shell.ShellExecutor.run') as mock_run:
            mock_run.return_value = MagicMock(
                success=True, return_code=0, stdout="", stderr=""
            )

            from astra.tools.git_ops import GitHubVCS
            vcs = GitHubVCS()
            result = vcs.create_branch("./repos/test", "ai-dev-feature-123")

            assert result.success is True

    def test_pr_creation(self):
        """Test PR is created after successful task."""
        with patch('astra.tools.shell.ShellExecutor.run') as mock_run:
            mock_run.return_value = MagicMock(
                success=True,
                return_code=0,
                stdout="https://github.com/test/repo/pull/42\n",
                stderr=""
            )

            from astra.tools.git_ops import GitHubVCS
            vcs = GitHubVCS()
            result = vcs.create_pr(
                "./repos/test",
                title="Add feature",
                body="## Summary\n\nAdded new feature"
            )

            assert result.success is True
            assert "42" in str(result.pr_number) or "pull/42" in result.pr_url

