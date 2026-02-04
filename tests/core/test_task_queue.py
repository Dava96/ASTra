from unittest.mock import MagicMock, patch

import pytest

from astra.core.task_queue import TaskQueue, TaskStatus


@pytest.fixture
def persist_path(tmp_path):
    return tmp_path / "tasks.json"


@pytest.fixture
def tq(persist_path):
    return TaskQueue(persist_path=str(persist_path))


def test_task_queue_add(tq):
    task = tq.add("feature", "req", "u1", "c1", "p1")
    assert task.id
    assert task.type == "feature"
    assert tq.get_task(task.id) == task


class SyncExecutor:
    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)
        return MagicMock()

    def shutdown(self, wait=True):
        pass


def test_task_queue_persistence(persist_path):
    with patch("astra.core.task_queue._io_executor", SyncExecutor()):
        q1 = TaskQueue(str(persist_path))
        task = q1.add("fix", "err", "u2", "c2")

        # Load in new queue
        q2 = TaskQueue(str(persist_path))
        assert q2.get_task(task.id).request == "err"


def test_task_queue_lifecycle(tq):
    t1 = tq.add("q", "r1", "u", "c")
    t2 = tq.add("q", "r2", "u", "c")

    # Get next
    current = tq.get_next()
    assert current.id == t1.id
    assert current.status == TaskStatus.RUNNING
    assert tq.get_current().id == t1.id

    # Position
    assert tq.get_position(t2.id) == 1

    # Complete
    tq.complete(current, success=True, result={"ok": True})
    assert current.status == TaskStatus.SUCCESS
    assert tq.get_current() is None
    assert len(tq.get_history()) == 1


def test_task_queue_cancel(tq):
    tq.add("type", "req", "u", "c")
    current = tq.get_next()

    assert not tq.is_cancel_requested()
    tq.cancel_current()
    assert tq.is_cancel_requested()

    tq.complete(current, success=False, error="cancelled")
    assert not tq.is_cancel_requested()


def test_task_history_filtering(tq):
    tq.add("t", "r1", "user1", "c")
    t2 = tq.add("t", "r2", "user2", "c")

    tq.complete(tq.get_next(), True)  # t1
    tq.complete(tq.get_next(), True)  # t2

    assert len(tq.get_history(user_id="user1")) == 1
    assert tq.get_last_result(user_id="user2").id == t2.id


def test_queue_status(tq):
    tq.add("t", "r", "u", "c")
    status = tq.get_queue_status()
    assert status["queued"] == 1
    assert status["current"] is None

    tq.get_next()
    status = tq.get_queue_status()
    assert status["queued"] == 0
    assert status["current"] is not None


def test_load_corrupted_data(persist_path):
    persist_path.write_text("invalid json")
    # Should not crash, just log error and start empty
    tq = TaskQueue(str(persist_path))
    assert tq.get_queue_status()["queued"] == 0
