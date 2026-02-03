import time

import pytest

from astra.core.monitor import Monitor
from astra.core.safeguard import Safeguard
from astra.core.task_queue import TaskQueue


@pytest.fixture
def monitor():
    return Monitor()

@pytest.fixture
def task_queue(tmp_path):
    persist_path = tmp_path / "test_queue.json"
    return TaskQueue(persist_path=str(persist_path))

@pytest.fixture
def safeguard():
    return Safeguard()

def test_monitor_caching(monitor):
    """Verify that Monitor health checks are cached (O(1))."""
    # First run to populate cache
    start = time.time()
    res1 = monitor.run_all_checks()
    dur1 = time.time() - start

    # Second run should be significantly faster
    start = time.time()
    res2 = monitor.run_all_checks()
    dur2 = time.time() - start

    assert res1 == res2
    # Cached run should be sub-millisecond, uncached usually >10ms
    assert dur2 < dur1
    assert dur2 < 0.005 # Less than 5ms for cached lookup

def test_task_queue_efficiency(task_queue):
    """Verify that TaskQueue operations are non-destructive and efficient."""
    # Add tasks
    tasks = []
    for i in range(10):
        t = task_queue.add("feature", f"Task {i}", "user", "channel")
        tasks.append(t)

    assert task_queue.qsize() == 10

    # Check position - should be O(N) but non-destructive
    pos = task_queue.get_position(tasks[5].id)
    assert pos == 6
    assert task_queue.qsize() == 10 # Queue preserved

    # Verify next task
    next_t = task_queue.get_next()
    assert next_t.id == tasks[0].id
    assert task_queue.qsize() == 9

def test_safeguard_repo_caching(safeguard):
    """Verify that Safeguard caches expensive GitHub API/Resource checks."""
    url = "https://github.com/google/astra"

    # Mocking would be better for CI, but this verifies the CACHING logic
    # if it already exists or on first real call.
    start = time.time()
    safeguard.check_repo_size(url)
    dur1 = time.time() - start

    start = time.time()
    safeguard.check_repo_size(url)
    dur2 = time.time() - start

    assert dur2 < dur1 if dur1 > 0.001 else True
    assert dur2 < 0.001 # Cached lookup should be near-zero

def test_safeguard_system_caching(safeguard):
    """Verify that system resource checks are cached."""
    start = time.time()
    safeguard.check_system_resources()
    dur1 = time.time() - start

    start = time.time()
    safeguard.check_system_resources()
    dur2 = time.time() - start

    assert dur2 <= dur1
    assert dur2 < 0.001
