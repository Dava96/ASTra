"""Tests for manifest parser."""

import json

from astra.tools.manifest import (
    format_manifest_for_context,
    get_project_manifest,
    parse_cargo_toml,
    parse_composer_json,
    parse_go_mod,
    parse_package_json,
    parse_pyproject_toml,
)


class TestPackageJsonParser:
    """Test package.json parsing."""

    def test_parse_full(self, tmp_path):
        pkg = {
            "name": "my-app",
            "version": "1.0.0",
            "scripts": {"test": "jest", "lint": "eslint .", "build": "webpack"},
            "dependencies": {"react": "^18.0.0"},
            "devDependencies": {"jest": "^29.0.0"},
        }

        pkg_file = tmp_path / "package.json"
        pkg_file.write_text(json.dumps(pkg))

        result = parse_package_json(pkg_file)

        assert result["name"] == "my-app"
        assert result["test_command"] == "jest"
        assert result["lint_command"] == "eslint ."
        assert "react" in result["dependencies"]
        assert "jest" in result["devDependencies"]

    def test_parse_minimal(self, tmp_path):
        pkg_file = tmp_path / "package.json"
        pkg_file.write_text('{"name": "simple"}')

        result = parse_package_json(pkg_file)

        assert result["name"] == "simple"
        assert result["test_command"] is None


class TestComposerJsonParser:
    """Test composer.json parsing."""

    def test_parse_full(self, tmp_path):
        composer = {
            "name": "vendor/app",
            "scripts": {"test": "phpunit", "lint": "phpstan analyse"},
            "require": {"php": "^8.0"},
            "require-dev": {"phpunit/phpunit": "^10.0"},
        }

        composer_file = tmp_path / "composer.json"
        composer_file.write_text(json.dumps(composer))

        result = parse_composer_json(composer_file)

        assert result["name"] == "vendor/app"
        assert result["test_command"] == "phpunit"
        assert "php" in result["require"]


class TestPyprojectTomlParser:
    """Test pyproject.toml parsing."""

    def test_parse_basic(self, tmp_path):
        content = """
[project]
name = "my-package"
version = "1.0.0"
dependencies = ["requests", "click"]

[project.optional-dependencies]
dev = ["pytest", "ruff"]
"""

        toml_file = tmp_path / "pyproject.toml"
        toml_file.write_text(content)

        result = parse_pyproject_toml(toml_file)

        assert result["name"] == "my-package"
        assert "requests" in result["dependencies"]


class TestGoModParser:
    """Test go.mod parsing."""

    def test_parse_basic(self, tmp_path):
        content = """module github.com/user/repo

go 1.21

require (
    github.com/pkg/errors v0.9.1
)
"""

        mod_file = tmp_path / "go.mod"
        mod_file.write_text(content)

        result = parse_go_mod(mod_file)

        assert result["name"] == "github.com/user/repo"
        assert result["test_command"] == "go test ./..."


class TestCargoTomlParser:
    """Test Cargo.toml parsing."""

    def test_parse_basic(self, tmp_path):
        content = """
[package]
name = "my-crate"
version = "0.1.0"

[dependencies]
serde = "1.0"

[dev-dependencies]
tokio = "1.0"
"""

        cargo_file = tmp_path / "Cargo.toml"
        cargo_file.write_text(content)

        result = parse_cargo_toml(cargo_file)

        assert result["name"] == "my-crate"
        assert "serde" in result["dependencies"]
        assert result["test_command"] == "cargo test"


class TestGetProjectManifest:
    """Test project manifest detection and parsing."""

    def test_detect_node_project(self, tmp_path):
        pkg = {"name": "node-app", "scripts": {"test": "jest"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        result = get_project_manifest(tmp_path)

        assert result["language"] == "javascript"
        assert result["test_command"] == "npm run test"

    def test_detect_typescript_project(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "ts-app"}')
        (tmp_path / "tsconfig.json").write_text("{}")

        result = get_project_manifest(tmp_path)

        assert result["language"] == "typescript"

    def test_detect_php_project(self, tmp_path):
        composer = {"name": "php/app", "scripts": {"test": "phpunit"}}
        (tmp_path / "composer.json").write_text(json.dumps(composer))

        result = get_project_manifest(tmp_path)

        assert result["language"] == "php"


class TestFormatManifest:
    """Test manifest context formatting."""

    def test_format_with_scripts(self):
        manifest = {
            "name": "my-app",
            "language": "javascript",
            "test_command": "npm test",
            "lint_command": "npm run lint",
            "scripts": {"test": "jest", "lint": "eslint .", "build": "webpack"},
            "dependencies": ["react", "lodash"],
        }

        context = format_manifest_for_context(manifest)

        assert "my-app" in context
        assert "javascript" in context
        assert "npm test" in context
        assert "Available Scripts" in context
        assert "jest" in context
        assert "Dependencies" in context
        assert "react" in context
