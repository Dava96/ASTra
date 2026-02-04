"""Base class for browser navigators."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NavigationResult:
    """Result of a navigation action."""

    success: bool
    element_found: bool = False
    action_performed: str = ""
    error_message: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class BaseNavigator(ABC):
    """Abstract base class for browser navigators."""

    name: str = ""
    description: str = ""

    def __init__(self, page=None):
        self.page = page  # Playwright page object

    def set_page(self, page):
        """Set the Playwright page object."""
        self.page = page

    @abstractmethod
    async def find_element(self, selector: str, **kwargs) -> Any:
        """Find an element using the navigator's strategy."""
        pass

    @abstractmethod
    async def perform_action(self, action: str, selector: str, **kwargs) -> NavigationResult:
        """Perform an action on an element."""
        pass
