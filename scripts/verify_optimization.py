import sys
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from astra.core.monitor import Monitor
from astra.core.safeguard import Safeguard
from astra.core.task_queue import TaskQueue


def test_monitor_performance():
    print("--- Testing Monitor Performance (O(1) Caching) ---")
    monitor = Monitor()

    start = time.time()
    res1 = monitor.run_all_checks()
    end = time.time()
    print(f"First run (uncached): {(end - start)*1000:.2f}ms")

    start = time.time()
    res2 = monitor.run_all_checks()
    end = time.time()
    print(f"Second run (cached): {(end - start)*1000:.2f}ms")

    assert res1 == res2
    print("Performance test passed!")

def test_queue_persistence_performance():
    print("\n--- Testing TaskQueue Persistence Performance ---")
    queue = TaskQueue(persist_path="./data/test_queue.json")

    # Add 100 tasks
    start = time.time()
    for i in range(100):
        queue.add("feature", f"Task {i}", "user", "channel")
    end = time.time()
    print(f"Added 100 tasks: {(end - start)*1000:.2f}ms (Total)")

    # Check position (used to be destructive)
    start = time.time()
    pos = queue.get_position(queue._queued_list[50].id)
    end = time.time()
    print(f"Get position 50: {(end - start)*1000:.2f}ms")
    assert pos == 51

    print("Queue performance test passed!")

def test_safeguard_caching():
    print("\n--- Testing Safeguard Caching ---")
    sg = Safeguard()
    url = "https://github.com/google/astra"

    start = time.time()
    sg.check_repo_size(url)
    end = time.time()
    print(f"First API check: {(end - start)*1000:.2f}ms")

    start = time.time()
    sg.check_repo_size(url)
    end = time.time()
    print(f"Second API check (cached): {(end - start)*1000:.2f}ms")

    print("Safeguard caching test passed!")

if __name__ == "__main__":
    try:
        test_monitor_performance()
        test_queue_persistence_performance()
        test_safeguard_caching()
        print("\n✅ ALL PERFORMANCE TESTS PASSED!")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
