"""Tests for language-aware manifest file detection."""

import tempfile
from pathlib import Path

import pytest

from astra.ingestion.parser import (
    LANGUAGE_MANIFEST_FILES,
    get_language_for_file,
    get_manifest_files_for_project,
)


class TestLanguageManifestMapping:
    """Test the language to manifest file mapping."""

    def test_javascript_manifests(self):
        """Test JavaScript has correct manifests."""
        assert "package.json" in LANGUAGE_MANIFEST_FILES["javascript"]

    def test_typescript_manifests(self):
        """Test TypeScript has correct manifests."""
        manifests = LANGUAGE_MANIFEST_FILES["typescript"]
        assert "package.json" in manifests
        assert "tsconfig.json" in manifests

    def test_php_manifests(self):
        """Test PHP has correct manifests."""
        manifests = LANGUAGE_MANIFEST_FILES["php"]
        assert "composer.json" in manifests
        assert "composer.lock" in manifests

    def test_python_manifests(self):
        """Test Python has correct manifests."""
        manifests = LANGUAGE_MANIFEST_FILES["python"]
        assert "pyproject.toml" in manifests
        assert "requirements.txt" in manifests

    def test_go_manifests(self):
        """Test Go has correct manifests."""
        manifests = LANGUAGE_MANIFEST_FILES["go"]
        assert "go.mod" in manifests
        assert "go.sum" in manifests

    def test_rust_manifests(self):
        """Test Rust has correct manifests."""
        manifests = LANGUAGE_MANIFEST_FILES["rust"]
        assert "Cargo.toml" in manifests


class TestGetManifestFilesForProject:
    """Test manifest file detection for projects."""

    @pytest.fixture
    def project_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_detect_javascript_project(self, project_dir):
        """Test detection of JavaScript project manifests."""
        # Create JS file to trigger detection
        (project_dir / "app.js").write_text("console.log('hello');")
        # Create package.json
        (project_dir / "package.json").write_text('{"name": "test", "version": "1.0.0"}')

        manifests = get_manifest_files_for_project(project_dir)

        assert "package.json" in manifests
        assert '"name": "test"' in manifests["package.json"]

    def test_detect_python_project(self, project_dir):
        """Test detection of Python project manifests."""
        (project_dir / "main.py").write_text("print('hello')")
        (project_dir / "pyproject.toml").write_text('[project]\nname = "test"')

        manifests = get_manifest_files_for_project(project_dir)

        assert "pyproject.toml" in manifests

    def test_detect_php_project(self, project_dir):
        """Test detection of PHP project manifests."""
        (project_dir / "index.php").write_text("<?php echo 'hello';")
        (project_dir / "composer.json").write_text('{"name": "vendor/package"}')

        manifests = get_manifest_files_for_project(project_dir)

        assert "composer.json" in manifests

    def test_detect_go_project(self, project_dir):
        """Test detection of Go project manifests."""
        (project_dir / "main.go").write_text("package main")
        (project_dir / "go.mod").write_text("module example.com/test")

        manifests = get_manifest_files_for_project(project_dir)

        assert "go.mod" in manifests

    def test_multi_language_project(self, project_dir):
        """Test project with multiple languages."""
        # JavaScript
        (project_dir / "app.js").write_text("console.log('hello');")
        (project_dir / "package.json").write_text('{"name": "test"}')
        # Python
        (project_dir / "script.py").write_text("print('hello')")
        (project_dir / "requirements.txt").write_text("requests==2.28.0")

        manifests = get_manifest_files_for_project(project_dir)

        assert "package.json" in manifests
        assert "requirements.txt" in manifests

    def test_missing_manifest(self, project_dir):
        """Test when manifest file doesn't exist."""
        (project_dir / "app.js").write_text("console.log('hello');")
        # No package.json

        manifests = get_manifest_files_for_project(project_dir)

        assert "package.json" not in manifests

    def test_empty_project(self, project_dir):
        """Test empty project directory."""
        manifests = get_manifest_files_for_project(project_dir)
        assert len(manifests) == 0

    def test_content_truncation(self, project_dir):
        """Test that large files are truncated."""
        (project_dir / "app.js").write_text("const x = 1;")
        # Create large package.json
        large_content = '{"name": "test", "data": "' + "x" * 5000 + '"}'
        (project_dir / "package.json").write_text(large_content)

        manifests = get_manifest_files_for_project(project_dir)

        # Should be truncated to 4000 chars
        assert len(manifests["package.json"]) <= 4000


class TestGetLanguageForFile:
    """Test file extension to language detection."""

    def test_javascript_extensions(self):
        assert get_language_for_file("app.js") == "javascript"
        assert get_language_for_file("app.jsx") == "javascript"
        assert get_language_for_file("app.mjs") == "javascript"

    def test_typescript_extensions(self):
        assert get_language_for_file("app.ts") == "typescript"
        assert get_language_for_file("app.tsx") == "tsx"

    def test_python_extension(self):
        assert get_language_for_file("script.py") == "python"

    def test_php_extension(self):
        assert get_language_for_file("index.php") == "php"

    def test_go_extension(self):
        assert get_language_for_file("main.go") == "go"

    def test_rust_extension(self):
        assert get_language_for_file("lib.rs") == "rust"

    def test_unknown_extension(self):
        assert get_language_for_file("file.xyz") is None
