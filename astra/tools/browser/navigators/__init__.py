"""Browser navigators package."""

from astra.tools.browser.navigators.base import BaseNavigator, NavigationResult
from astra.tools.browser.navigators.registry import (
    get_navigator,
    get_navigator_names,
    register_navigator,
)

__all__ = ["BaseNavigator", "NavigationResult", "get_navigator", "register_navigator", "get_navigator_names"]
