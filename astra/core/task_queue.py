"""FIFO Task Queue with persistence and status tracking."""

import concurrent.futures
import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

# Global executor for background persistence
_io_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task execution status."""
    QUEUED = "queued"
    PLANNING = "planning"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """Represents a task in the queue."""
    id: str
    type: str  # feature, fix, quick
    request: str
    user_id: str
    channel_id: str
    project: str | None = None
    status: TaskStatus = TaskStatus.QUEUED
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    token_usage: dict[str, int] | None = None
    attempts: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @property
    def duration_seconds(self) -> float | None:
        """Calculate task duration in seconds."""
        if not self.started_at or not self.completed_at:
            return None
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.completed_at)
        return (end - start).total_seconds()

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Create from dictionary."""
        data["status"] = TaskStatus(data["status"])
        return cls(**data)


class TaskQueue:
    """Thread-safe FIFO task queue with persistence."""

    def __init__(self, persist_path: str = "./data/task_queue.json"):
        self._queued_list: list[Task] = []
        self._current_task: Task | None = None
        self._history: list[Task] = []
        self._lut: dict[str, Task] = {} # Lookup table for O(1) accessing
        self._lock = threading.RLock()
        self._persist_path = Path(persist_path)
        self._cancel_requested = False

        self._load()

    def qsize(self) -> int:
        """Get number of items in the queue."""
        return len(self._queued_list)

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID from anywhere (queue, current, history)."""
        return self._lut.get(task_id)

    def update(self, task: Task) -> None:
        """Update a task's state and persist."""
        if task.id in self._lut:
            self._lut[task.id] = task
            self._save()
        else:
            logger.warning(f"Attempted to update unknown task {task.id}")

    def _load(self) -> None:
        """Load queue state from disk."""
        if self._persist_path.exists():
            try:
                with open(self._persist_path) as f:
                    data = json.load(f)

                # Restore queued tasks
                for task_data in data.get("queued", []):
                    task = Task.from_dict(task_data)
                    self._queued_list.append(task)
                    self._lut[task.id] = task

                # Restore history
                self._history = [Task.from_dict(t) for t in data.get("history", [])]
                for task in self._history:
                    self._lut[task.id] = task

                logger.info(f"Loaded {len(self._queued_list)} queued tasks and {len(self._history)} history entries")
            except Exception as e:
                logger.error(f"Failed to load task queue: {e}")

    def _save(self) -> None:
        """Persist queue state to disk."""
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            queued = [t.to_dict() for t in self._queued_list]
            history = [t.to_dict() for t in self._history[-50:]]

        data = {
            "queued": queued,
            "history": history
        }

        def _persist_worker(data_dict):
             try:
                temp_path = self._persist_path.with_suffix(".tmp")
                with open(temp_path, "w") as f:
                    json.dump(data_dict, f, indent=2)
                temp_path.replace(self._persist_path)
             except Exception as e:
                 logger.error(f"Background save failed: {e}")

        # Fire and forget (fire_and_forget logic)
        _io_executor.submit(_persist_worker, data)

    def add(self, task_type: str, request: str, user_id: str, channel_id: str, project: str | None = None) -> Task:
        """Add a new task to the queue."""
        task = Task(
            id=str(uuid4())[:8],
            type=task_type,
            request=request,
            user_id=user_id,
            channel_id=channel_id,
            project=project
        )

        with self._lock:
            self._queued_list.append(task)
            self._lut[task.id] = task
            self._save()

        logger.info(f"Task {task.id} added to queue. Position: {len(self._queued_list)}")
        return task

    def get_next(self) -> Task | None:
        """Get the next task from the queue."""
        with self._lock:
            if not self._queued_list:
                return None

            task = self._queued_list.pop(0)
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(UTC).isoformat()
            self._current_task = task
            self._save()

        logger.info(f"Starting task {task.id}: {task.request[:50]}...")
        return task

    def complete(self, task: Task, success: bool, result: dict | None = None, error: str | None = None) -> None:
        """Mark a task as complete."""
        with self._lock:
            task.status = TaskStatus.SUCCESS if success else TaskStatus.FAILED
            task.completed_at = datetime.now(UTC).isoformat()
            task.result = result
            task.error = error
            self._history.append(task)
            self._current_task = None
            self._cancel_requested = False
            self._save()

        status = "succeeded" if success else "failed"
        logger.info(f"Task {task.id} {status}")

    def cancel_current(self) -> bool:
        """Request cancellation of the current task."""
        if self._current_task:
            self._cancel_requested = True
            logger.info(f"Cancellation requested for task {self._current_task.id}")
            return True
        return False

    def is_cancel_requested(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancel_requested

    def get_current(self) -> Task | None:
        """Get the currently running task."""
        return self._current_task

    def get_queue_status(self) -> dict:
        """Get queue status summary."""
        with self._lock:
            return {
                "queued": len(self._queued_list),
                "current": self._current_task.to_dict() if self._current_task else None,
                "recent": [t.to_dict() for t in self._history[-5:]]
            }

    def get_position(self, task_id: str) -> int | None:
        """Get position of a task in the queue ($O(N)$ non-destructive)."""
        with self._lock:
            for i, task in enumerate(self._queued_list):
                if task.id == task_id:
                    return i + 1
        return None

    def get_last_result(self, user_id: str | None = None) -> Task | None:
        """Get the last completed task, optionally filtered by user."""
        for task in reversed(self._history):
            if user_id is None or task.user_id == user_id:
                return task
        return None

    def get_history(self, limit: int = 10, user_id: str | None = None) -> list[Task]:
        """Get recent task history, optionally filtered by user."""
        if user_id:
            filtered = [t for t in self._history if t.user_id == user_id]
            return list(reversed(filtered[-limit:]))
        return list(reversed(self._history[-limit:]))

    def get_interrupted_tasks(self) -> list[Task]:
        """Get tasks that were running when the bot last stopped."""
        return [t for t in self._history if t.status == TaskStatus.RUNNING]
