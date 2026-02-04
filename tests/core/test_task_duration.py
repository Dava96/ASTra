"""Tests for Task duration property and TaskQueue."""

import pytest

from astra.core.task_queue import Task, TaskQueue, TaskStatus


class TestTaskDuration:
    """Test Task duration_seconds property."""

    def test_duration_when_completed(self):
        """Test duration calculation for completed task."""
        task = Task(
            id="test-1",
            type="feature",
            request="Test request",
            user_id="123",
            channel_id="456",
            started_at="2024-01-01T12:00:00+00:00",
            completed_at="2024-01-01T12:05:30+00:00",  # 5min 30sec later
        )

        assert task.duration_seconds == 330  # 5*60 + 30

    def test_duration_when_not_started(self):
        """Test duration returns None when not started."""
        task = Task(
            id="test-3",
            type="feature",
            request="Test request",
            user_id="123",
            channel_id="456",
            started_at=None,
            completed_at=None,
        )

        assert task.duration_seconds is None


class TestTaskQueueOperations:
    """Test TaskQueue operations."""

    @pytest.fixture
    def queue(self, tmp_path):
        return TaskQueue(persist_path=str(tmp_path / "test_queue.json"))

    def test_add_and_get_next(self, queue):
        """Test adding and retrieving tasks."""
        task = queue.add(
            task_type="feature",
            request="Add login",
            user_id="user1",
            channel_id="channel1",
            project="my-project",
        )

        assert task.id is not None
        assert task.status == TaskStatus.QUEUED

        next_task = queue.get_next()
        assert next_task.id == task.id
        assert next_task.status == TaskStatus.RUNNING

    def test_queue_status(self, queue):
        """Test queue status reporting."""
        # Add multiple tasks
        queue.add("feature", "Task 1", "u1", "c1")
        queue.add("feature", "Task 2", "u1", "c1")

        # Get one (makes it current)
        queue.get_next()

        status = queue.get_queue_status()
        assert status["queued"] == 1
        assert status["current"] is not None  # Fixed: uses 'current' not 'running'

    def test_complete_task(self, queue):
        """Test completing a task."""
        task = queue.add("feature", "Test", "u1", "c1")
        queue.get_next()  # Start it

        queue.complete(task, success=True, result={"output": "done"})

        assert task.status == TaskStatus.SUCCESS
        assert task.result == {"output": "done"}

    def test_get_position(self, queue):
        """Test getting task position in queue."""
        task1 = queue.add("feature", "First", "u1", "c1")
        task2 = queue.add("feature", "Second", "u1", "c1")
        task3 = queue.add("feature", "Third", "u1", "c1")

        assert queue.get_position(task1.id) == 1
        assert queue.get_position(task2.id) == 2
        assert queue.get_position(task3.id) == 3

    def test_history_filtering(self, queue):
        """Test history filtering by user."""
        task1 = queue.add("feature", "Task 1", "user1", "c1")
        task2 = queue.add("feature", "Task 2", "user2", "c1")

        # Complete both
        queue.get_next()
        queue.complete(task1, success=True)
        queue.get_next()
        queue.complete(task2, success=True)

        history = queue.get_history(limit=10, user_id="user1")
        assert len(history) == 1
        assert history[0].user_id == "user1"
