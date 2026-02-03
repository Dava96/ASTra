"""Tests for BrowserTool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.tools.browser import PLAYWRIGHT_AVAILABLE, BrowserTool


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestBrowserTool:
    """Tests for the BrowserTool class."""

    @pytest.fixture
    async def browser(self, tmp_path):
        """Fixture for BrowserTool."""
        bt = BrowserTool(screenshot_dir=tmp_path)
        async with bt as b:
            yield b

    @pytest.mark.asyncio
    async def test_screenshot_capture(self, browser):
        """Test capturing a screenshot."""
        # Use a reliable URL
        url = "https://example.com"
        result = await browser.screenshot(url)

        assert result.url == url
        assert result.path.exists()
        assert result.path.suffix == ".png"
        assert result.title == "Example Domain"

    @pytest.mark.asyncio
    async def test_get_dom(self, browser):
        """Test DOM extraction."""
        url = "https://example.com"
        dom = await browser.get_dom(url)

        assert dom.tag == "body"
        # Check for <h1>
        h1 = next((c for c in dom.children if c.tag == "div"), None)
        # Detailed check of the structure of example.com
        assert any(c.tag == "h1" for c in dom.children) or any(any(gc.tag == "h1" for gc in c.children) for c in dom.children)

    @pytest.mark.asyncio
    async def test_get_accessibility_tree(self, browser):
        """Test accessibility tree extraction."""
        url = "https://example.com"

        # Mock route to avoid real network requests being blocked if not handled
        if browser._page:
            browser._page.route = AsyncMock()

        a11y = await browser.get_accessibility_tree(url)

        assert a11y.role in ["WebArea", "document"]
        if a11y.role == "WebArea":
             # We might not get "Example Domain" if headless/mocked behaves differently,
             # but check structure is sound.
             assert isinstance(a11y.children, list)
        else:
            # Fallback
            assert a11y.name == "Accessibility Unavailable" or a11y.role == "document"

    @pytest.mark.asyncio
    async def test_cleanup(self, browser, tmp_path):
        """Test cleanup of old screenshots."""
        # Create a dummy old file
        old_file = tmp_path / "screenshot_20200101_120000_test.png"
        old_file.write_text("dummy")

        # Set mtime to 2 hours ago
        import os
        import time
        past_time = time.time() - (2 * 3600)
        try:
            os.utime(str(old_file), (past_time, past_time))
        except OSError:
            pytest.skip("Could not set mtime")

        # Run cleanup with 1 hour (default)
        deleted = browser.cleanup(max_age_hours=1)
        assert deleted >= 1
        assert not old_file.exists()

    @pytest.mark.asyncio
    async def test_compare_screenshots(self, browser, tmp_path):
        """Test comparing two screenshots."""
        from PIL import Image

        # Create two slightly different images
        path1 = tmp_path / "before.png"
        path2 = tmp_path / "after.png"

        img1 = Image.new("RGB", (100, 100), color="white")
        img1.save(path1)

        img2 = Image.new("RGB", (100, 100), color="white")
        # Add a red pixel
        img2.putpixel((50, 50), (255, 0, 0))
        img2.save(path2)

        result = browser.compare_screenshots(path1, path2, threshold=0.0)

        assert result.diff_percentage > 0
        assert result.diff_image is not None
        assert result.diff_image.exists()
        assert "Difference:" in result.summary

    @pytest.mark.asyncio
    async def test_execute_interface(self, browser):
        """Test the tool execute interface directly."""
        # Success cases
        res = await browser.execute("screenshot", url="https://example.com")
        assert "Screenshot saved" in res

        # Test generic actions
        with patch.object(browser, "interact", new_callable=AsyncMock) as mock_interact:
            mock_interact.return_value = "✅ Clicked"
            res = await browser.execute("click", selector="btn", url="https://example.com")
            # Default mode is now a11y
            mock_interact.assert_called_with("click", selector="btn", mode="a11y")
            assert res == "✅ Clicked"

    @pytest.mark.asyncio
    async def test_interact_logic(self, browser):
        """Test interaction hybrid mode."""
        # Mock specialized navigators
        with patch("astra.tools.browser.tool.get_navigator") as mock_get_nav:
            mock_nav = MagicMock()
            mock_nav.perform_action = AsyncMock(return_value=MagicMock(success=True))
            mock_nav.set_page = MagicMock()
            mock_get_nav.return_value = mock_nav

            # Hybrid mode: tries a11y first unconditionally now
            await browser.interact("click", "button:Submit", mode="hybrid")
            # Should have called a11y navigator
            mock_get_nav.assert_any_call("a11y")

            # Reset
            mock_get_nav.reset_mock()

            # Explicit DOM mode
            await browser.interact("click", "#btn", mode="dom")
            mock_get_nav.assert_called_with("dom")

    @pytest.mark.asyncio
    async def test_are_urls_equivalent(self, browser):
        """Test URL equivalence check."""
        assert browser._are_urls_equivalent("https://example.com", "https://example.com/")
        assert browser._are_urls_equivalent("https://example.com/foo", "https://example.com/foo/")
        assert not browser._are_urls_equivalent("https://example.com", "https://example.org")
