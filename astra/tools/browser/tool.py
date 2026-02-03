"""Browser tool for visual verification and navigation."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from astra.config import get_config
from astra.core.tools import BaseTool
from astra.tools.browser.models import (
    A11yNode,
    ComparisonResult,
    DOMElement,
    ScreenshotResult,
)
from astra.tools.browser.navigators.registry import get_navigator
from astra.tools.browser.scripts import DOM_EXTRACTION_SCRIPT

logger = logging.getLogger(__name__)

# Try to import playwright
try:
    from playwright.async_api import Browser, Route, async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Run: pip install playwright && playwright install chromium")

# Try to import Pillow
try:
    from PIL import Image, ImageChops
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow not installed. Run: pip install Pillow")


class BrowserTool(BaseTool):
    """Headless browser for visual verification and navigation."""

    name = "browser_action"
    description = (
        "Capture screenshots, extract DOM/A11y trees, or interact with pages using "
        "hybrid A11y-first navigation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["screenshot", "dom", "a11y", "click", "type", "get_text"],
                "description": "Action to perform"
            },
            "url": {
                "type": "string",
                "description": "The URL to visit (optional for subsequent actions)"
            },
            "selector": {
                "type": "string",
                "description": "Selector (e.g., 'button:Submit' for A11y, or CSS/XPath)"
            },
            "text": {
                "type": "string",
                "description": "Text to type (for type action)"
            },
            "full_page": {
                "type": "boolean",
                "description": "Capture full page screenshot",
                "default": False
            },
            "mode": {
                "type": "string",
                "enum": ["hybrid", "a11y", "dom"],
                "description": "Navigation mode (default: a11y)",
                "default": "a11y"
            }
        },
        "required": ["action"]
    }

    def __init__(
        self,
        screenshot_dir: str | Path | None = None,
        viewport: tuple[int, int] = (1280, 720),
        headless: bool = True
    ):
        config = get_config()
        self._screenshot_dir = Path(
            screenshot_dir or
            config.get("browser", "screenshot_dir", default="./data/screenshots")
        )
        self._viewport = viewport
        self._headless = headless
        self._browser: Browser | None = None
        self._playwright = None
        self._page = None  # Persistent page for session
        self._cleanup_hours = config.get("browser", "cleanup_after_hours", default=1)

        # Ensure screenshot directory exists
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def start(self):
        """Start the browser."""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright not installed. Run: pip install playwright && playwright install chromium")

        if not self._playwright:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self._headless)
            logger.info("Browser started")

    async def stop(self):
        """Stop the browser and cleanup."""
        if self._page:
            await self._page.close()
            self._page = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Browser stopped")

    async def _get_page(self):
        """Get or create the current page."""
        if not self._browser:
            await self.start()
        if not self._page:
            self._page = await self._browser.new_page(
                viewport={"width": self._viewport[0], "height": self._viewport[1]}
            )
        return self._page

    def _normalize_url(self, url: str) -> str:
        """Ensure URL has a protocol, respecting data URLs."""
        if not url:
            return ""
        if "://" not in url and not url.startswith("data:"):
            return f"https://{url}"
        return url

    def _are_urls_equivalent(self, url1: str, url2: str) -> bool:
        """Check if two URLs are effectively the same."""
        if not url1 or not url2:
            return url1 == url2
        u1 = self._normalize_url(url1).rstrip("/")
        u2 = self._normalize_url(url2).rstrip("/")
        return u1 == u2

    async def execute(self, action: str, url: str | None = None, **kwargs: Any) -> Any:
        """Execute the requested tool action."""
        if url:
            url = self._normalize_url(url)
            try:
                page = await self._get_page()
                if not self._are_urls_equivalent(page.url, url):
                    # Blocking resources for faster loading on data extraction
                    if action in ["dom", "a11y", "get_text"]:
                         await page.route("**/*", lambda route: route.abort()
                            if route.request.resource_type in ["image", "media", "font", "stylesheet"]
                            else route.continue_())

                    wait_until = "domcontentloaded" if action in ["dom", "a11y", "get_text"] else "load"
                    await page.goto(url, timeout=kwargs.get("timeout_ms", 30000), wait_until=wait_until)
            except Exception as e:
                return f"❌ Failed to load URL: {e}"

        if action in ["click", "type", "get_text"]:
            # Move known args out of kwargs to avoid multiple values
            sel = kwargs.pop("selector", None)
            m = kwargs.pop("mode", "a11y")
            return await self.interact(action, selector=sel, mode=m, **kwargs)
        elif action == "screenshot":
            if not url and not self._page:
                 return "❌ URL required for initial screenshot"
            res = await self.screenshot(url or self._page.url, **kwargs) # type: ignore
            if not res: return "❌ Screenshot failed"
            return f"✅ Screenshot saved to {res.path} (URL: {res.url})"
        elif action == "dom":
            if not url and not self._page: return "❌ URL required"
            res = await self.get_dom(url or self._page.url, **kwargs) # type: ignore
            if isinstance(res, str): return res
            return self.format_dom_summary(res)
        elif action == "a11y":
            if not url and not self._page: return "❌ URL required"
            res = await self.get_accessibility_tree(url or self._page.url, **kwargs) # type: ignore
            if isinstance(res, str): return res
            return self.format_a11y_summary(res)
        else:
            return f"❌ Unknown action: {action}"

    async def interact(self, action: str, selector: str | None = None, mode: str = "a11y", **kwargs) -> str:
        """Perform interaction using configured navigator."""
        if not selector:
            return "❌ Selector required for interaction"

        page = await self._get_page()

        # Helper to run an action with a specific navigator
        async def run_nav(nav_name):
            nav = get_navigator(nav_name)
            if not nav:
                return None
            nav.set_page(page)
            return await nav.perform_action(action, selector, **kwargs)

        result = None

        # Hybrid Mode: Try A11y first, then DOM
        if mode == "hybrid":
             # Prioritize A11y for everything in hybrid mode
            result = await run_nav("a11y")
            if result and result.success:
                data = f" Data: {result.data}" if result.data else ""
                return f"✅ {action} on '{selector}' (A11y){data}"

            # Fallback to DOM
            result = await run_nav("dom")
            if result and result.success:
                data = f" Data: {result.data}" if result.data else ""
                return f"✅ {action} on '{selector}' (DOM){data}"

        elif mode == "a11y":
            result = await run_nav("a11y")
            if result and result.success:
                data = f" Data: {result.data}" if result.data else ""
                return f"✅ {action} on '{selector}' (A11y){data}"

        elif mode == "dom":
            result = await run_nav("dom")
            if result and result.success:
                data = f" Data: {result.data}" if result.data else ""
                return f"✅ {action} on '{selector}' (DOM){data}"

        # Fallthrough for failure or unknown mode (shouldn't happen with enum)
        if result and result.success:
             # Should be covered above, but safety net
             data = f" Data: {result.data}" if result.data else ""
             return f"✅ {action} on '{selector}' ({mode}){data}"

        error = result.error_message if result else "Unknown error"
        return f"❌ Interaction failed: {error}"

    async def screenshot(
        self,
        url: str,
        full_page: bool = False,
        selector: str | None = None,
        wait_for: str | None = None,
        timeout_ms: int = 30000
    ) -> ScreenshotResult:
        """Capture screenshot."""
        url = self._normalize_url(url)
        page = await self._get_page()

        if not self._are_urls_equivalent(page.url, url):
            await page.goto(url, timeout=timeout_ms)

        if wait_for:
            await page.wait_for_selector(wait_for, timeout=timeout_ms)

        start_time = datetime.now(UTC)
        timestamp = start_time.strftime("%Y%m%d_%H%M%S")
        safe_url = url.replace("://", "_").replace("/", "_")[:50]
        filename = f"screenshot_{timestamp}_{safe_url}.png"
        path = self._screenshot_dir / filename

        if selector:
            element = await page.query_selector(selector)
            if element:
                await element.screenshot(path=str(path))
            else:
                logger.warning(f"Selector {selector} not found, capturing full page")
                await page.screenshot(path=str(path), full_page=full_page)
        else:
            await page.screenshot(path=str(path), full_page=full_page)

        load_time_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        return ScreenshotResult(
            path=path,
            url=url,
            viewport=self._viewport,
            full_page=full_page,
            timestamp=start_time.isoformat(),
            title=await page.title(),
            load_time_ms=load_time_ms
        )

    async def get_dom(self, url: str, max_depth: int = 10, timeout_ms: int = 30000) -> DOMElement:
        """Extract clean DOM."""
        url = self._normalize_url(url)
        page = await self._get_page()
        if not self._are_urls_equivalent(page.url, url):
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")


        data = await page.evaluate(DOM_EXTRACTION_SCRIPT, max_depth)
        return self._parse_dom_data(data)

    def _parse_dom_data(self, data: dict) -> DOMElement:
        if not data: return DOMElement(tag="body")
        return DOMElement(
            tag=data.get("tag", "unknown"),
            id=data.get("id"),
            classes=data.get("classes", []),
            text=data.get("text"),
            role=data.get("role"),
            attributes=data.get("attributes", {}),
            children=[self._parse_dom_data(c) for c in data.get("children", [])]
        )

    async def get_accessibility_tree(self, url: str, timeout_ms: int = 30000) -> A11yNode:
        """Extract A11y tree."""
        url = self._normalize_url(url)
        page = await self._get_page()
        if not self._are_urls_equivalent(page.url, url):
            # A11y doesn't need full layout, but safer to respect some loading
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

        # Safety check for Playwright versions or mocks that might lack accessibility
        if not hasattr(page, "accessibility"):
            logger.warning("Page object missing accessibility attribute")
            return A11yNode(role="document", name="Accessibility Unavailable")

        snapshot = await page.accessibility.snapshot()
        return self._parse_a11y_node(snapshot) if snapshot else A11yNode(role="document", name="Unavailable")

    def _parse_a11y_node(self, data: dict) -> A11yNode:
        return A11yNode(
            role=data.get("role", "unknown"),
            name=data.get("name", ""),
            value=data.get("value"),
            description=data.get("description"),
            keyshortcuts=data.get("keyshortcuts"),
            focused=data.get("focused", False),
            disabled=data.get("disabled", False),
            children=[self._parse_a11y_node(c) for c in data.get("children", [])]
        )

    def cleanup(self, max_age_hours: int | None = None) -> int:
        """Delete old screenshots."""
        if max_age_hours is None:
            max_age_hours = self._cleanup_hours

        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        count = 0

        for path in self._screenshot_dir.glob("screenshot_*.png"):
            try:
                # Use mtime
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                if mtime < cutoff:
                    path.unlink()
                    count += 1
            except Exception as e:
                logger.warning(f"Failed to delete {path}: {e}")

        logger.info(f"Cleaned up {count} old screenshots")
        return count

    def compare_screenshots(self, before: Path, after: Path, threshold: float = 0.05) -> ComparisonResult:
        """Compare screenshots (Pillow wrapper)."""
        if not PILLOW_AVAILABLE:
            return ComparisonResult(None, 0.0, True, "Pillow missing")

        try:
            img1 = Image.open(before).convert("RGB")
            img2 = Image.open(after).convert("RGB")
            if img1.size != img2.size: img2 = img2.resize(img1.size)

            diff = ImageChops.difference(img1, img2)
            if not diff.getbbox():
                return ComparisonResult(None, 0.0, True, "Identical")

            # Save diff image
            diff_path = self._screenshot_dir / f"diff_{int(datetime.now().timestamp())}.png"
            diff.save(diff_path)

            # Simple diff logic for brevity
            hist = diff.convert("L").histogram()
            diff_pixels = sum(hist[20:]) # Ignore noise
            pct = diff_pixels / (img1.size[0] * img1.size[1])

            return ComparisonResult(diff_path, pct, pct < threshold, f"Difference: {pct:.2%}")
        except Exception as e:
            return ComparisonResult(None, 1.0, False, f"Error: {e}")

    # Format helpers (kept from original)
    def format_dom_summary(self, dom: DOMElement, max_lines: int = 50) -> str:
        lines = []
        def traverse(el, indent=0):
            if len(lines) >= max_lines: return
            p = "  " * indent
            meta = []
            if el.id: meta.append(f'#{el.id}')
            if el.role: meta.append(f'[{el.role}]')
            if el.text: meta.append(f'"{el.text}"')
            meta_str = f" {' '.join(meta)}" if meta else ""
            lines.append(f"{p}<{el.tag}{meta_str}>")
            for c in el.children: traverse(c, indent + 1)
        traverse(dom)
        return "\n".join(lines)

    def format_a11y_summary(self, node: A11yNode, max_lines: int = 5000) -> str:
        lines = []
        def traverse(n, indent=0):
            if len(lines) >= max_lines: return
            p = "  " * indent
            # Enhanced details
            details = []
            if n.value: details.append(f"val='{n.value}'")
            if n.keyshortcuts: details.append(f"keys='{n.keyshortcuts}'")
            if n.focused: details.append("[FOCUSED]")
            if n.disabled: details.append("[DISABLED]")
            detail_str = f" ({', '.join(details)})" if details else ""

            lines.append(f"{p}[{n.role}] {n.name}{detail_str}")
            for c in n.children: traverse(c, indent + 1)
        traverse(node)
        return "\n".join(lines)


# Synchronous wrappers
def capture_screenshot(url: str, **kwargs) -> ScreenshotResult:
    async def _run():
        async with BrowserTool() as b: return await b.screenshot(url, **kwargs)
    return asyncio.run(_run())
