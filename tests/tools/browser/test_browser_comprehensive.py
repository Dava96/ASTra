import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import astra.tools.browser.tool as browser_tool_mod
from astra.tools.browser.models import A11yNode, DOMElement, ScreenshotResult
from astra.tools.browser.navigators.base import BaseNavigator, NavigationResult
from astra.tools.browser.navigators.registry import (
    get_navigator,
    register_navigator,
)
from astra.tools.browser.tool import BrowserTool, capture_screenshot


@pytest.fixture
def browser_tool():
    with patch("astra.tools.browser.tool.get_config") as mock_config:

        def mock_get(*args, **kwargs):
            if "cleanup_after_hours" in args:
                return 1
            if "screenshot_dir" in args:
                return "./data/screenshots"
            return kwargs.get("default")

        mock_config.return_value.get.side_effect = mock_get
        return BrowserTool()


def get_async_page_mock():
    pm = MagicMock()
    pm.goto = AsyncMock()
    pm.route = AsyncMock()
    pm.evaluate = AsyncMock(return_value={"tag": "body", "children": []})
    pm.screenshot = AsyncMock(return_value=b"data")
    pm.wait_for_selector = AsyncMock()
    pm.title = AsyncMock(return_value="Title")
    pm.accessibility = MagicMock()
    pm.accessibility.snapshot = AsyncMock(
        return_value={"role": "root", "name": "n", "children": []}
    )

    el = MagicMock()
    el.screenshot = AsyncMock(return_value=b"d")
    pm.query_selector = AsyncMock(return_value=el)

    loc = MagicMock()
    loc.count = AsyncMock(return_value=1)
    loc.first = MagicMock()
    loc.first.click = AsyncMock()
    loc.first.fill = AsyncMock()
    loc.first.inner_text = AsyncMock(return_value="t")
    pm.locator = MagicMock(return_value=loc)
    pm.get_by_role = MagicMock(return_value=loc)

    pm.url = "http://test"
    return pm


# --- Model Tests ---


def test_models_exhaustive():
    res = ScreenshotResult(Path("t.png"), "u", (1, 1), False, "now", "T", 1)
    assert res.to_dict()["load_time_ms"] == 1
    p = DOMElement(tag="div", id="r", classes=["c"], text="t", role="main", attributes={"a": "v"})
    p.children = [DOMElement(tag="p")]
    assert p.to_dict()["children"][0]["tag"] == "p"
    n = A11yNode(role="btn", name="n", value="v", description="d", states=["s"])
    n.children = [A11yNode(role="text", name="t")]
    assert n.to_dict()["children"][0]["name"] == "t"


# --- Registry & Base Tests ---


def test_registry_and_base():
    class TestNav(BaseNavigator):
        name = "test_nav"

        async def find_element(self, selector, **kwargs):
            return "el"

        async def perform_action(self, action, selector, **kwargs):
            return NavigationResult(success=True)

    register_navigator(TestNav)
    assert get_navigator("test_nav") is not None
    assert get_navigator("inv_nav") is None

    class BadNav(BaseNavigator):
        name = ""

        async def find_element(self, s, **kw):
            pass

        async def perform_action(self, a, s, **kw):
            pass

    with pytest.raises(ValueError):
        register_navigator(BadNav)
    tn = TestNav()
    tn.set_page("p")
    assert tn.page == "p"


# --- Tool Lifecycle & Context ---


@pytest.mark.asyncio
async def test_lifecycle_context(browser_tool):
    with patch("astra.tools.browser.tool.async_playwright") as mock_pw_func:
        mock_pw = AsyncMock()
        mock_pw_func.return_value = mock_pw
        mock_pw.start.return_value = mock_pw
        mock_browser = AsyncMock()
        mock_pw.chromium.launch.return_value = mock_browser
        async with browser_tool as b:
            assert b._browser is not None
            await b.start()
            # Hit new_page branch
            await b._get_page()
        await b.stop()
        await b.stop()


# --- Tool Dispatch Logic (100% Core) ---


@pytest.mark.asyncio
async def test_tool_dispatch_100(browser_tool):
    pm = get_async_page_mock()
    browser_tool._page = pm

    await browser_tool.execute("dom", url="http://t")
    await browser_tool.execute("screenshot", full_page=True)
    await browser_tool.execute("screenshot", selector="#b")
    await browser_tool.execute("a11y", url="http://t")

    # Interaction
    assert "✅" in await browser_tool.execute("click", selector="#b", mode="dom")

    # Formatters
    dom = DOMElement(tag="div", id="i", role="r", text="t")
    dom.children = [DOMElement(tag="span")]
    assert "div" in browser_tool.format_dom_summary(dom)
    a11y = A11yNode(role="button", name="btn")
    a11y.children = [A11yNode(role="text", name="txt")]
    assert "button" in browser_tool.format_a11y_summary(a11y)

    # dispatch errors
    assert "Unknown action" in await browser_tool.execute("unknown")
    browser_tool._page = None
    assert "URL required" in await browser_tool.execute("dom")
    assert "URL required" in await browser_tool.execute("a11y")
    assert "URL required" in await browser_tool.execute("screenshot")


@pytest.mark.asyncio
async def test_errors_and_fallbacks_exhaustive(browser_tool):
    pm = get_async_page_mock()
    # Trigger error in execute top-level try block
    # Ensure goto is AsyncMock so it can be awaited
    pm.goto = AsyncMock(side_effect=Exception("Page.goto: Protocol error"))
    browser_tool._page = pm
    # Check that the exception is caught and formatted as an error string
    res = await browser_tool.execute("dom", url="http://err")
    assert "Protocol error" in res

    # Reset goto for sub-call tests
    pm.goto.side_effect = None
    pm.accessibility.snapshot.return_value = None
    assert (await browser_tool.get_accessibility_tree("http://t")).name == "Unavailable"

    # screenshot branches
    pm.query_selector.return_value = None
    await browser_tool.screenshot("http://t", selector="#miss")

    # Validating that execute handles exceptions is done above.
    # Direct calls to get_dom/screenshot would raise if page fails, not return None.
    pass


@pytest.mark.asyncio
async def test_interact_logic_exhaustive(browser_tool):
    pm = get_async_page_mock()
    browser_tool._page = pm
    assert "Selector required" in await browser_tool.interact("click")

    with patch("astra.tools.browser.tool.get_navigator", return_value=None):
        assert "Interaction failed" in await browser_tool.interact("click", "btn")

    n_ok = MagicMock()
    n_ok.perform_action = AsyncMock(return_value=NavigationResult(success=True, data={"v": 1}))
    with patch("astra.tools.browser.tool.get_navigator", return_value=n_ok):
        assert "(A11y)" in await browser_tool.interact("click", "role:btn", mode="hybrid")
        assert "(A11y)" in await browser_tool.interact("click", "btn", mode="a11y")
        assert "(DOM)" in await browser_tool.interact("click", "btn", mode="dom")

    # Hybrid fallback
    n_a = MagicMock()
    n_a.perform_action = AsyncMock(return_value=NavigationResult(success=False))
    n_d = MagicMock()
    n_d.perform_action = AsyncMock(return_value=NavigationResult(success=True))
    with patch(
        "astra.tools.browser.tool.get_navigator", side_effect=lambda n: n_a if n == "a11y" else n_d
    ):
        assert "(DOM)" in await browser_tool.interact("click", "btn", mode="hybrid")

        # Unreachable branch in interact for 100%
        n_a.perform_action.return_value = NavigationResult(success=False, error_message="msg")
        n_d.perform_action.return_value = NavigationResult(success=False, error_message="msg")
        assert "msg" in await browser_tool.interact("click", "btn")


@pytest.mark.asyncio
async def test_nav_impls_pure_100():
    from astra.tools.browser.navigators.implementations.a11y import A11yNavigator
    from astra.tools.browser.navigators.implementations.dom import DOMNavigator

    class MockLocator:
        def __init__(self, c):
            self.count = AsyncMock(side_effect=c)
            self.first = MagicMock()
            self.first.click = AsyncMock()
            self.first.fill = AsyncMock()
            self.first.inner_text = AsyncMock(return_value="t")

    # A11y
    a = A11yNavigator()
    a.page = MagicMock()
    # Find regex hit
    locR = MockLocator([0, 1])
    a.page.get_by_role.side_effect = lambda *r, **kw: locR
    assert await a.find_element("r:n") is locR.first
    # Actions
    with patch.object(a, "find_element", return_value=locR.first):
        await a.perform_action("click", "r:s")
        await a.perform_action("type", "r:s", text="h")
        await a.perform_action("get_text", "r:s")
        assert (await a.perform_action("un", "r:s")).success is False
        locR.first.click.side_effect = Exception("e")
        await a.perform_action("click", "r:s")
    # Not found / Exception
    with patch.object(a, "find_element", return_value=None):
        assert (await a.perform_action("click", "r:s")).success is False
    a.page.get_by_role.side_effect = Exception("f")
    assert await a.find_element("r:n") is None

    # DOM
    d = DOMNavigator()
    d.page = MagicMock()
    locD = MockLocator([1])
    d.page.locator.side_effect = lambda s: locD
    assert await d.find_element("#i") is locD.first
    d.page.locator.side_effect = Exception("f")
    assert await d.find_element("#i") is None
    with patch.object(d, "find_element", return_value=locD.first):
        await d.perform_action("click", "#i")
        await d.perform_action("type", "#i", text="h")
        await d.perform_action("get_text", "#i")
        assert (await d.perform_action("un", "#i")).success is False
        locD.first.click.side_effect = Exception("e")
        await d.perform_action("click", "#i")


def test_cleanup_and_compare_100(browser_tool, tmp_path):
    browser_tool._screenshot_dir = tmp_path
    f1 = tmp_path / "screenshot_old.png"
    f1.write_text("o")
    os.utime(str(f1), (0, 0))
    with patch("astra.tools.browser.tool.Path.unlink", side_effect=[Exception("f"), None]):
        browser_tool.cleanup()
        browser_tool.cleanup()

    with patch("PIL.Image.open") as m_open:
        img = MagicMock()
        img.size = (1, 1)
        img.convert.return_value = img
        m_open.return_value = img
        with patch("PIL.ImageChops.difference") as m_diff:
            m_diff.return_value.getbbox.return_value = [0, 0, 1, 1]
            m_diff.return_value.convert.return_value.histogram.return_value = [0] * 256
            m_diff.return_value.convert.return_value.histogram.return_value[200] = 100
            assert "Difference" in browser_tool.compare_screenshots("p1", "p2").summary
            m_diff.return_value.getbbox.return_value = None
            assert "Identical" in browser_tool.compare_screenshots("p1", "p2").summary
        m_open.side_effect = Exception("err")
        assert "err" in browser_tool.compare_screenshots("p1", "p2").summary

    with patch.object(browser_tool_mod, "PILLOW_AVAILABLE", False):
        assert "Pillow missing" in browser_tool.compare_screenshots("p1", "p2").summary


def test_wrappers_100():
    with patch.object(browser_tool_mod, "PLAYWRIGHT_AVAILABLE", False), pytest.raises(
        ImportError
    ):
        asyncio.run(BrowserTool().start())
    with patch.object(browser_tool_mod, "PILLOW_AVAILABLE", False):
        assert "Pillow missing" in BrowserTool().compare_screenshots("p1", "p2").summary
    with patch("astra.tools.browser.tool.BrowserTool") as MT:
        mi = AsyncMock()
        MT.return_value = mi
        mi.__aenter__.return_value = mi
        mi.screenshot.return_value = ScreenshotResult(Path("p"), "u", (1, 1), False, "n", "T", 1)
        assert capture_screenshot("u").url == "u"
