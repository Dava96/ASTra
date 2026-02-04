import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(str(Path.cwd()))

# Import Orchestrator after sys.path update
from astra.core.orchestrator import Orchestrator
from astra.core.template_manager import TemplateManager


class TestContextAndIsolation(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.project_path = self.test_dir / "test_project"
        self.project_path.mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("astra.core.orchestrator.LiteLLMClient")
    @patch("astra.core.orchestrator.ChromaDBStore")
    @patch("astra.core.orchestrator.KnowledgeGraph")
    def test_file_isolation(self, MockKG, MockStore, MockLLM):
        """Verify .astra directory creation and gitignore update."""
        # Mock orchestrator dependencies
        class MockGateway: pass

        # We need to mock internals that __init__ calls
        # We need to mock internals that __init__ calls
        with patch("astra.core.orchestrator.TaskQueue"), \
             patch("astra.core.orchestrator.ASTParser"), \
             patch("astra.core.orchestrator.GitHubVCS"), \
             patch("astra.core.orchestrator.ShellExecutor"), \
             patch("astra.core.orchestrator.FileOps"), \
             patch("astra.core.orchestrator.AiderTool"), \
             patch("astra.core.orchestrator.TemplateManager"), \
             patch("astra.core.orchestrator.ToolRegistry"), \
             patch("astra.core.orchestrator.ContextGatherer"), \
             patch("astra.tools.scheduler.service.SchedulerService"), \
             patch("astra.tools.scheduler.tool.CronTool"):

            orch = Orchestrator(gateway=MockGateway())

        # Test _ensure_astra_dir
        astra_dir = orch._ensure_astra_dir(str(self.project_path))

        # Check directory
        self.assertTrue(astra_dir.exists())
        self.assertTrue(astra_dir.is_dir())
        self.assertEqual(astra_dir.name, ".astra")

        # Check .gitignore
        gitignore = self.project_path / ".gitignore"
        self.assertTrue(gitignore.exists())
        content = gitignore.read_text()
        self.assertIn(".astra/", content)

        # Test idempotency (run again)
        orch._ensure_astra_dir(str(self.project_path))
        content = gitignore.read_text()
        self.assertEqual(content.count(".astra/"), 1)

    @patch("astra.core.architecture.TemplateManager")
    @patch("astra.core.architecture.FileOps")
    @patch("astra.core.architecture.LiteLLMClient")
    def test_architecture_location(self, MockLLM, MockFileOps, MockTM):
        """Verify ARCHITECTURE.md is generated in .astra folder."""
        from astra.core.architecture import ArchitectureGenerator

        # Configure mocks
        mock_llm = MockLLM.return_value

        async def mock_chat(*args, **kwargs):
            m = MagicMock()
            m.content = "ARCH CONTENT"
            return m

        mock_llm.chat.side_effect = mock_chat

        # Async helper
        import asyncio

        gen = ArchitectureGenerator()

        # Run async method
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(gen.generate_if_missing(str(self.project_path)))
        finally:
            loop.close()

        # Check file location
        astra_arch = self.project_path / ".astra" / "ARCHITECTURE.md"
        self.assertTrue(astra_arch.exists(), "ARCHITECTURE.md not found in .astra/")
        self.assertEqual(astra_arch.read_text(), "ARCH CONTENT")

        # Ensure root file was NOT created
        root_arch = self.project_path / "ARCHITECTURE.md"
        self.assertFalse(root_arch.exists(), "ARCHITECTURE.md found in root (should be in .astra/)")

    def test_template_rendering(self):
        """Verify templates include context and plan variables."""
        tm = TemplateManager()

        # Test Planning Template
        context_data = "CRITICAL_CONTEXT_DATA"
        rendered_plan = tm.render("planning_feature", request="Task", context=context_data)
        self.assertIn(context_data, rendered_plan, "Context not found in planning template")

        # Test Critic Template
        plan_data = "PROPOSED_IMPLEMENTATION_PLAN"
        rendered_critic = tm.render("critic_review", request="Task", plan=plan_data)
        self.assertIn(plan_data, rendered_critic, "Plan not found in critic template")

    def test_plan_location(self):
        """Verify implementation plan is saved to .astra folder."""
        # Setup mocks for Orchestrator._plan
        # We need a partial mock of Orchestrator or just instantiate with mocks
        class MockConfig:
            def get(self, *args, **kwargs):
                if "critic_enabled" in args or "critic_enabled" in kwargs:
                    return True
                return kwargs.get("default", "mock_value")
            @property
            def llm(self):
                mock = MagicMock()
                mock.model = "test-model"
                return mock

        class MockGateway:
            async def send_message(self, *args, **kwargs): pass

        with patch("astra.core.orchestrator.TaskQueue"), \
             patch("astra.core.orchestrator.ASTParser"), \
             patch("astra.core.orchestrator.GitHubVCS"), \
             patch("astra.core.orchestrator.ShellExecutor"), \
             patch("astra.core.orchestrator.FileOps"), \
             patch("astra.core.orchestrator.AiderTool"), \
             patch("astra.core.orchestrator.TemplateManager"), \
             patch("astra.core.orchestrator.ToolRegistry") as MockToolRegistry, \
             patch("astra.core.orchestrator.ContextGatherer") as MockContextGatherer, \
             patch("astra.core.orchestrator.LiteLLMClient") as MockLLM, \
             patch("astra.core.orchestrator.ChromaDBStore"), \
             patch("astra.core.orchestrator.KnowledgeGraph"), \
             patch("astra.tools.scheduler.service.SchedulerService"), \
             patch("astra.tools.scheduler.tool.CronTool"):

            orch = Orchestrator(gateway=MockGateway(), config=MockConfig())

            # Setup context and plan
            from astra.core.orchestrator import Task, TaskContext

            context = TaskContext(
                task=Task(
                    id="task-123",
                    request="Test Task",
                    channel_id="channel-1",
                    type="chat",
                    user_id="user-1"
                ),
                project_path=str(self.project_path),
                collection_name="test_col",
                branch_name="branch-1"
            )

            # Mock _generate_initial_plan return
            orch._generate_initial_plan = MagicMock()

            async def mock_gen_plan(*args):
                return {"content": "# Plan", "tokens": 10}
            orch._generate_initial_plan.side_effect = mock_gen_plan


            async def mock_gather(*args, **kwargs):
                return "Context"
            MockContextGatherer.return_value.gather.side_effect = mock_gather

            # Mock templates
            orch._templates = MagicMock()
            orch._templates.render.return_value = "Critic Prompt"

            # Configure Critic LLM
            mock_critic_llm = MagicMock()
            async def mock_critic_chat(*args, **kwargs):
                m = MagicMock()
                m.content = "Critic Approved"
                return m
            mock_critic_llm.chat.side_effect = mock_critic_chat
            orch._llm.for_critic.return_value = mock_critic_llm

            # Run _plan
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(orch._plan(context))
            finally:
                loop.close()

            # Verify context passed to templates
            # 1. Initial Plan
            # mock_gen_plan.assert_called() checks are done inside _generate_initial_plan mock ideally or here
            # Mock templates
            orch._templates = MagicMock()
            orch._templates.render.return_value = "Critic Prompt"
            # 2. Critic Review
            orch._templates.render.assert_any_call(
                "critic_review",
                plan="# Plan",
                request="Test Task",
                context="Context"
            )

            # Verify file location
            astra_plan = self.project_path / ".astra" / "implementation_plan_task-123.md"
            self.assertTrue(astra_plan.exists(), "Plan not found in .astra/")
            self.assertIn("# Plan", astra_plan.read_text())

            # Verify return contains filename
            self.assertEqual(result["filename"], "implementation_plan_task-123.md")

if __name__ == "__main__":
    unittest.main()
