"""Data models for browser tool."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ScreenshotResult:
    """Result of a screenshot capture."""

    path: Path
    url: str
    viewport: tuple[int, int]
    full_page: bool
    timestamp: str
    title: str
    load_time_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "url": self.url,
            "viewport": list(self.viewport),
            "full_page": self.full_page,
            "timestamp": self.timestamp,
            "title": self.title,
            "load_time_ms": self.load_time_ms,
        }


@dataclass
class DOMElement:
    """Cleaned DOM element representation."""

    tag: str
    id: str | None = None
    classes: list[str] = field(default_factory=list)
    text: str | None = None
    role: str | None = None
    children: list["DOMElement"] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {"tag": self.tag}
        if self.id:
            result["id"] = self.id
        if self.classes:
            result["classes"] = self.classes
        if self.text:
            result["text"] = self.text[:100]  # Truncate
        if self.role:
            result["role"] = self.role
        if self.attributes:
            result["attributes"] = self.attributes
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


@dataclass
class A11yNode:
    """Accessibility tree node."""

    role: str
    name: str
    value: str | None = None
    description: str | None = None
    keyshortcuts: str | None = None
    focused: bool = False
    disabled: bool = False
    states: list[str] = field(default_factory=list)
    children: list["A11yNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = {"role": self.role, "name": self.name}
        if self.value:
            result["value"] = self.value
        if self.description:
            result["description"] = self.description
        if self.keyshortcuts:
            result["keyshortcuts"] = self.keyshortcuts
        if self.focused:
            result["focused"] = True
        if self.disabled:
            result["disabled"] = True
        if self.states:
            result["states"] = self.states
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


@dataclass
class ComparisonResult:
    """Result of comparing two screenshots."""

    diff_image: Path | None
    diff_percentage: float
    structurally_similar: bool
    summary: str
