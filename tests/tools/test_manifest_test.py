import json

from astra.tools.manifest import (
    get_project_manifest,
    parse_composer_json,
    parse_package_json,
    parse_pyproject_toml,
)


def test_parse_package_json(tmp_path):
    pkg_file = tmp_path / "package.json"
    pkg_file.write_text(
        json.dumps(
            {"name": "test-pkg", "scripts": {"build": "tsc"}, "dependencies": {"react": "18"}}
        )
    )

    data = parse_package_json(pkg_file)
    assert data["name"] == "test-pkg"
    assert data["scripts"]["build"] == "tsc"
    assert "react" in data["dependencies"]


def test_parse_composer_json(tmp_path):
    comp_file = tmp_path / "composer.json"
    comp_file.write_text(
        json.dumps(
            {"name": "vendor/pkg", "scripts": {"test": "phpunit"}, "require": {"php": ">=8.0"}}
        )
    )

    data = parse_composer_json(comp_file)
    assert data["name"] == "vendor/pkg"
    assert data["test_command"] == "phpunit"


def test_parse_pyproject_toml(tmp_path):
    toml_file = tmp_path / "pyproject.toml"
    # Basic TOML content
    toml_file.write_text(
        '[project]\nname = "astra"\ndependencies = ["requests"]\n'
        '[tool.poetry.scripts]\nstart = "main:run"\n',
        encoding="utf-8",
    )

    data = parse_pyproject_toml(toml_file)
    assert data["name"] == "astra"
    assert "requests" in data["dependencies"]
    assert data["scripts"]["start"] == "main:run"


def test_get_project_manifest_priority(tmp_path):
    # If both exist, package.json preferred? (actually order is JS, PHP, Python...)
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pyproject.toml").write_text("{}")

    manifest = get_project_manifest(tmp_path)
    assert manifest["language"] in ["javascript", "typescript"]


def test_parse_errors(tmp_path):
    # Invalid JSON
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{broken")
    assert parse_package_json(bad_file) == {}
    assert parse_composer_json(bad_file) == {}

    # Invalid TOML
    bad_toml = tmp_path / "bad.toml"
    bad_toml.write_text("broken = [")
    assert parse_pyproject_toml(bad_toml) == {}
