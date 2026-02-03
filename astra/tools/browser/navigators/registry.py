"""Registry for browser navigators."""

import logging

from astra.tools.browser.navigators.base import BaseNavigator

logger = logging.getLogger(__name__)

# Global registry
NAVIGATOR_REGISTRY: dict[str, type[BaseNavigator]] = {}


def register_navigator(cls: type[BaseNavigator]) -> type[BaseNavigator]:
    """Decorator to register a navigator class."""
    if not cls.name:
        raise ValueError(f"Navigator {cls.__name__} must define a 'name' attribute")

    NAVIGATOR_REGISTRY[cls.name] = cls
    logger.debug(f"Registered navigator: {cls.name}")
    return cls


def get_navigator(name: str) -> BaseNavigator | None:
    """Get a navigator instance by name."""
    nav_cls = NAVIGATOR_REGISTRY.get(name)
    if nav_cls:
        return nav_cls()
    return None

def get_navigator_names() -> list[str]:
    """Get list of registered navigator names."""
    return list(NAVIGATOR_REGISTRY.keys())

# Import implementations to trigger registration
# This must be at the bottom to avoid circular imports
from astra.tools.browser.navigators.implementations import a11y, dom  # noqa: E402, F401
