"""DOM-based navigator."""

from astra.tools.browser.navigators.base import BaseNavigator, NavigationResult


def _register_dom(cls):
    """Delayed registration to avoid circular import."""
    from astra.tools.browser.navigators.registry import register_navigator
    return register_navigator(cls)

@_register_dom
class DOMNavigator(BaseNavigator):
    """Navigator using CSS selectors or XPath."""

    name = "dom"
    description = "Navigate using standard CSS selectors or XPath."

    async def find_element(self, selector: str, **kwargs):
        """Find element using CSS/XPath."""
        try:
            locator = self.page.locator(selector)
            if await locator.count() > 0:
                return locator.first
        except Exception:
            pass
        return None

    async def perform_action(self, action: str, selector: str, **kwargs) -> NavigationResult:
        """Perform action using DOM locator."""
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
