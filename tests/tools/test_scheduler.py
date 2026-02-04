"""Tests for Cron Scheduler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from astra.config import SchedulerConfig, get_config
from astra.tools.scheduler.tool import CronTool


@pytest_asyncio.fixture
async def scheduler_db(tmp_path):
    """Fixture for temporary scheduler service with config injection."""
    # Reset singleton if exists
    import astra.tools.scheduler.service as service_mod

    service_mod._SERVICE_INSTANCE = None

    db_path = f"sqlite:///{tmp_path}/test_scheduler.db"

    # Create config with enabled scheduler and high memory limit for testing
    config = get_config()
    config.scheduler = SchedulerConfig(
        enabled=True,
        db_path=db_path,
        resource_guard_enabled=True,
        max_memory_percent=100,  # Ensure tests don't fail on busy system unless we mock
    )

    service = service_mod.SchedulerService(config)
    # Inject into singleton for tool usage
    service_mod._SERVICE_INSTANCE = service

    service.start()
    yield service
    service.stop()
    service_mod._SERVICE_INSTANCE = None


@pytest.mark.asyncio
async def test_cron_tool_schedule_and_list(scheduler_db):
    """Test scheduling and O(1) listing."""
    tool = CronTool()

    result = await tool.execute(
        "schedule",
        cron="* * * * *",
        command="echo hello",
        description="Test Job",
        project_path="/tmp/project1",
    )

    assert "✅ Scheduled job" in result

    # Test List for specific project (should hit cache)
    jobs = scheduler_db.list_jobs("/tmp/project1")
    assert len(jobs) == 1
    assert jobs[0]["command"] == "echo hello"
    assert jobs[0]["project"] == "/tmp/project1"

    # Test List for another project (should be empty via cache)
    result_other = await tool.execute("list", project_path="/tmp/project2")
    assert "No active cron jobs" in result_other


@pytest.mark.asyncio
async def test_cron_tool_run_now(scheduler_db):
    """Test run_now feature."""
    tool = CronTool()

    # Schedule a job first
    res = await tool.execute(
        "schedule", cron="* * * * *", command="echo manual_run", project_path="/tmp"
    )
    import re

    match = re.search(r"ID: ([a-zA-Z0-9\.\-]+)", res)
    job_id = match.group(1)

    # Run Now
    # We need to mock the wrapper since it runs a shell command
    with patch(
        "astra.tools.scheduler.service.execute_job_wrapper", new_callable=AsyncMock
    ) as mock_wrapper:
        mock_wrapper.return_value = "Manual Run Executed"

        result = await tool.execute("run_now", job_id=job_id)
        assert "✅ Job triggered manually" in result
        assert "Manual Run Executed" in result

        # Verify wrapper called with correct guards
        mock_wrapper.assert_called_once()
        args = mock_wrapper.call_args[0]
        assert args[0] == "echo manual_run"  # command
        assert args[1] == "/tmp"  # path
        assert args[2] is True  # resource_guard default
        assert args[3] == 100  # max_memory from fixture


@pytest.mark.asyncio
async def test_cron_tool_health(scheduler_db):
    """Test health check."""
    tool = CronTool()

    result = await tool.execute("health")
    assert "Scheduler Health: HEALTHY" in result
    assert "Active Jobs: 0" in result
    assert "DB Connected: True" in result


@pytest.mark.asyncio
async def test_resource_guard_skips_execution():
    """Test that resource guard prevents execution on high memory."""
    from astra.tools.scheduler.service import execute_job_wrapper

    # Mock psutil to return 95% memory usage
    with patch("astra.tools.scheduler.service.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value.percent = 95.0

        # Wrapper configured with 90% max
        res = await execute_job_wrapper(
            "echo skip", "/tmp", resource_guard=True, max_memory_percent=90
        )

        assert "⚠️ Job execution skipped" in res
        assert "95.0% > 90%" in res


@pytest.mark.asyncio
async def test_job_cancellation(scheduler_db):
    """Test cancelling a job updates cache correctly."""
    tool = CronTool()
    await tool.execute(
        "schedule", cron="* * * * *", command="echo cancel_me", project_path="/tmp/cancel"
    )

    # Verify added
    jobs = scheduler_db.list_jobs("/tmp/cancel")
    assert len(jobs) == 1
    job_id = jobs[0]["id"]

    # Cancel
    result = await tool.execute("cancel", job_id=job_id)
    assert "✅ Cancelled job" in result

    # Verify removed from cache/list
    jobs_after = scheduler_db.list_jobs("/tmp/cancel")
    assert len(jobs_after) == 0


@pytest.mark.asyncio
async def test_job_completion_listener(scheduler_db):
    """Test that job completion events update status cache."""
    # We can't easily wait for real APScheduler events in unit tests without arbitrary sleeps.
    # So we call the listener manually to verify logic.
    from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent

    # Simulate Success
    event_success = JobExecutionEvent(
        code=EVENT_JOB_EXECUTED, job_id="job123", jobstore="default", scheduled_run_time=None
    )
    scheduler_db._on_job_completed(event_success)

    assert scheduler_db._job_status_cache["job123"]["status"] == "success"

    # Simulate Failure
    event_fail = JobExecutionEvent(
        code=EVENT_JOB_ERROR,
        job_id="job124",
        jobstore="default",
        scheduled_run_time=None,
        exception=Exception("Boom"),
    )
    scheduler_db._on_job_completed(event_fail)

    assert scheduler_db._job_status_cache["job124"]["status"] == "failed"
    assert "Boom" in scheduler_db._job_status_cache["job124"]["error"]


@pytest.mark.asyncio
async def test_run_job_now_errors(scheduler_db):
    """Test error handling in run_job_now."""
    # 1. Job not found
    res = await scheduler_db.run_job_now("non_existent")
    assert "Job non_existent not found" in res

    # 2. Execution error (mock wrapper raising)
    tool = CronTool()
    await tool.execute("schedule", cron="* * * * *", command="echo fail", project_path="/tmp")
    jobs = scheduler_db.list_jobs("/tmp")
    job_id = jobs[0]["id"]

    with patch(
        "astra.tools.scheduler.service.execute_job_wrapper", side_effect=Exception("Wrapper failed")
    ):
        res = await scheduler_db.run_job_now(job_id)
        assert "Failed to run job: Wrapper failed" in res


@pytest.mark.asyncio
async def test_health_check_degraded_fake_scheduler():
    """Test health check logic with simple Fake object."""
    from astra.tools.scheduler.service import SchedulerService

    class FakeScheduler:
        running = True

        def get_jobs(self):
            raise Exception("DB Error")

    # Mock config
    mock_config = MagicMock()
    mock_config.scheduler.enabled = True
    mock_config.scheduler.db_path = "sqlite:///:memory:"

    service = SchedulerService(mock_config)
    service._scheduler = FakeScheduler()
    service._started = True

    status = service.health_check()
    assert status["status"] == "degraded"
    assert status["db_connected"] is False


@pytest.mark.asyncio
async def test_cron_tool_schedule_exception():
    """Test exception during scheduling."""
    tool = CronTool()
    # Mock service.schedule_job to raise
    with patch.object(tool._service, "schedule_job", side_effect=Exception("Schedule Failed")):
        res = await tool.execute("schedule", cron="*", command="cmd")
        assert "Failed to schedule job: Schedule Failed" in res


@pytest.mark.asyncio
async def test_cron_tool_cancel_failure():
    """Test cancel failure."""
    tool = CronTool()
    # Mock service.cancel_job to return False
    with patch.object(tool._service, "cancel_job", return_value=False):
        res = await tool.execute("cancel", job_id="bad_id")
        assert "Job bad_id not found" in res


@pytest.mark.asyncio
async def test_cron_tool_list_formatting(scheduler_db):
    """Test list formatting with different statuses."""
    tool = CronTool()

    # Manually inject jobs into cache/scheduler mock for listing
    # It's easier to just use the public API and then modify the internal cache
    await tool.execute("schedule", cron="* * * * *", command="echo success", project_path="/tmp")
    await tool.execute("schedule", cron="* * * * *", command="echo fail", project_path="/tmp")

    jobs = scheduler_db.list_jobs("/tmp")
    id_success = jobs[0]["id"]
    id_fail = jobs[1]["id"]

    # Inject status
    scheduler_db._job_status_cache[id_success] = {"status": "success", "error": None}
    scheduler_db._job_status_cache[id_fail] = {"status": "failed", "error": "Timeout"}

    res = await tool.execute("list", project_path="/tmp")
    assert "🟢" in res  # Success icon
    assert "🔴" in res  # Fail icon
    assert "Timeout" in res  # Error message checks


@pytest.mark.asyncio
async def test_cron_tool_top_level_exception():
    """Test top-level exception handling in tool.execute."""
    tool = CronTool()
    # Mock _schedule to raise
    with patch.object(tool, "_schedule", side_effect=Exception("Unexpected")):
        res = await tool.execute("schedule", cron="*")
        assert "Error executing cron action: Unexpected" in res


@pytest.mark.asyncio
async def test_async_execute_real_call(scheduler_db):
    """Test _async_execute calling shell tool (mocked tool)."""
    from astra.tools.scheduler.service import _async_execute

    with patch("astra.tools.shell.ShellExecutor") as mock_shell_cls:
        mock_instance = mock_shell_cls.return_value
        mock_instance.execute = AsyncMock(return_value="Shell result")

        res = await _async_execute("echo real", "/tmp")
        assert res == "Shell result"

        # Test failure
        mock_instance.execute.side_effect = Exception("Shell failed")
        res_fail = await _async_execute("echo fail", "/tmp")
        assert "Error: Shell failed" in res_fail


@pytest.mark.asyncio
async def test_cron_tool_validation_errors():
    """Test validation errors in CronTool."""
    tool = CronTool()

    # Schedule missing args
    res = await tool.execute("schedule", cron="* * * * *")  # Missing command
    assert "cron' and 'command' are required" in res

    # Cancel missing job_id
    res = await tool.execute("cancel")
    assert "'job_id' is required" in res

    # Run Now missing job_id
    res = await tool.execute("run_now")
    assert "'job_id' is required" in res

    # Unknown action
    res = await tool.execute("unknown_action")
    assert "Unknown action" in res
