from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryNode:
    """Represents a single memory item."""

    id: str
    content: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None  # Similarity score if from recall


@dataclass
class MemoryOperationResult:
    """Structured result from a memory operation."""

    success: bool
    action: str
    message: str
    data: list[MemoryNode] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "message": self.message,
            "data": [
                {
                    "id": m.id,
                    "content": m.content,
                    "tags": m.tags,
                    "metadata": m.metadata,
                    "score": m.score,
                }
                for m in (self.data or [])
            ],
            "metadata": self.metadata,
        }
