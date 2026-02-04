from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.tools.scheduler.service import SchedulerService, execute_job_wrapper


@pytest.mark.asyncio
class TestScheduledOrchestration:
    """Integration test for SchedulerService and ShellExecutor."""

    @pytest.fixture
    def mock_config(self, tmp_path):
        config = MagicMock()
        # Explicitly set scheduler sub-mock
        scheduler_mock = MagicMock()
        scheduler_mock.enabled = True
        scheduler_mock.db_path = str(tmp_path / "jobs.db")
        scheduler_mock.coalesce = True
        scheduler_mock.misfire_grace_time = 60
        scheduler_mock.resource_guard_enabled = False
        scheduler_mock.max_memory_percent = 90
        config.scheduler = scheduler_mock
        return config

    @pytest.fixture
    async def scheduler_service(self, mock_config):
        service = SchedulerService(mock_config)
        service.start()
        yield service
        service.stop()

    async def test_schedule_and_run_now(self, scheduler_service, tmp_path):
        """Test scheduling a job and running it immediately."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # We need to mock ShellExecutor within the job wrapper because it's imported lazily
        with patch("astra.tools.shell.ShellExecutor") as mock_shell_cls:
            mock_shell = mock_shell_cls.return_value
            mock_shell.execute = AsyncMock(return_value={
                "success": True,
                "stdout": "Hello from scheduler",
                "stderr": "",
                "code": 0
            })

            # Schedule a job
            job_id = scheduler_service.schedule_job(
                command="echo 'Hello'",
                cron_expression="0 0 * * *", # Run at midnight
                project_path=str(project_dir),
                description="Test Job"
            )

            assert job_id is not None

            # Run it now
            result_msg = await scheduler_service.run_job_now(job_id)

            assert "✅ Job triggered manually" in result_msg
            assert "Hello from scheduler" in result_msg

            # Verify shell tool was called correctly
            mock_shell.execute.assert_called_once_with("echo 'Hello'", cwd=str(project_dir))

            # Verify status was updated in cache
            # Note: run_job_now calls execute_job_wrapper directly in this implementation,
            # but usually it's the listener that updates the cache.
            # In our implementation of run_job_now, it returns the result directly.

    async def test_resource_guard_triggers(self, scheduler_service, tmp_path):
        """Test that resource guard blocks execution if memory is high."""
        scheduler_service._scheduler_config.resource_guard_enabled = True
        scheduler_service._scheduler_config.max_memory_percent = 10 # Force mismatch

        # Mock psutil
        with patch("astra.tools.scheduler.service.psutil") as mock_psutil:
            mock_psutil.virtual_memory.return_value.percent = 80

            result = await execute_job_wrapper(
                command="echo 'test'",
                project_path=str(tmp_path),
                resource_guard=True,
                max_memory_percent=10
            )

            assert "⚠️ Job execution skipped" in result
            assert "System memory 80% > 10%" in result
