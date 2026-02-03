"""Accessibility-based navigator."""

import re

from astra.tools.browser.navigators.base import BaseNavigator, NavigationResult


def _register_a11y(cls):
    """Delayed registration to avoid circular import."""
    from astra.tools.browser.navigators.registry import register_navigator
    return register_navigator(cls)

@_register_a11y
class A11yNavigator(BaseNavigator):
    """Navigator using accessibility tree roles and names."""

    name = "a11y"
    description = "Navigate using semantic roles (button, link) and accessible names."

    async def find_element(self, selector: str, **kwargs):
        """Find element using role and name.
        
        Selector format: "role:name" (e.g. "button:Submit")
        """
        if ":" not in selector:
            return None

        role, name = selector.split(":", 1)
        role = role.strip()
        name = name.strip()

        try:
            # Use Playwright's get_by_role
            locator = self.page.get_by_role(role, name=name, exact=True)
            if await locator.count() > 0:
                return locator.first

            # Try partial match if exact failed
            locator = self.page.get_by_role(role, name=re.compile(re.escape(name), re.IGNORECASE))
            if await locator.count() > 0:
                return locator.first

        except Exception:
            pass
        return None

    async def perform_action(self, action: str, selector: str, **kwargs) -> NavigationResult:
        """Perform action using A11y locator."""
        element = await self.find_element(selector)

        if not element:
            return NavigationResult(success=False, error_message=f"Element not found: {selector}")

        try:
            if action == "click":
                await element.click()
            elif action == "type":
                text = kwargs.get("text", "")
                await element.fill(text)
            elif action == "get_text":
                text = await element.inner_text()
                return NavigationResult(success=True, element_found=True, action_performed=action, data={"text": text})
            else:
                 return NavigationResult(success=False, error_message=f"Unknown action: {action}")

            return NavigationResult(success=True, element_found=True, action_performed=action)

        except Exception as e:
            return NavigationResult(success=False, element_found=True, error_message=str(e))
