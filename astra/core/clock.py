import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Protocol for time-keeping to allow for deterministic testing."""

    def now(self) -> float:
        """Return the current time in seconds."""
        ...


class SystemClock:
    """Default implementation using system time."""

    def now(self) -> float:
        return time.time()
