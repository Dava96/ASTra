"""Tests for TemplateManager."""

import pytest

from astra.core.template_manager import TemplateManager


class TestTemplateManager:
    @pytest.fixture
    def tm(self, tmp_path):
        return TemplateManager(template_dir=tmp_path / "tpls")

    def test_create_defaults(self, tm, tmp_path):
        """Test defaults are created on init."""
        tpl_dir = tmp_path / "tpls"
        assert tpl_dir.exists()
        assert (tpl_dir / "planning_feature.md").exists()

    def test_get_template_cached(self, tm, tmp_path):
        # Create custom
        f = tmp_path / "tpls" / "custom.md"
        f.write_text("content", encoding="utf-8")

        # Read
        assert tm.get_template("custom") == "content"

        # Modify file - cache should return old
        f.write_text("new", encoding="utf-8")
        assert tm.get_template("custom") == "content"

        # Reset cache
        tm.reset_cache()
        assert tm.get_template("custom") == "new"

    def test_render(self, tm, tmp_path):
        f = tmp_path / "tpls" / "hello.md"
        f.write_text("Hello {{user_name}}!", encoding="utf-8")

        res = tm.render("hello", user_name="World")
        assert res == "Hello World!"

    def test_update_template(self, tm, tmp_path):
        tm.update_template("test", "version1")
        assert tm.get_template("test") == "version1"
        assert (tmp_path / "tpls" / "test.md").read_text(encoding="utf-8") == "version1"

    def test_missing_template(self, tm):
        with pytest.raises(FileNotFoundError):
            tm.get_template("nonexistent")
