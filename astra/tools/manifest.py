"""Manifest file parser for extracting scripts and dependencies."""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

logger = logging.getLogger(__name__)


def parse_package_json(file_path: str | Path) -> dict[str, Any]:
    """Parse package.json for scripts, dependencies, and metadata."""
    try:
        content = Path(file_path).read_text(encoding="utf-8")
        data = json.loads(content)

        return {
            "name": data.get("name", ""),
            "version": data.get("version", ""),
            "scripts": data.get("scripts", {}),
            "dependencies": list(data.get("dependencies", {}).keys()),
            "devDependencies": list(data.get("devDependencies", {}).keys()),
            "test_command": data.get("scripts", {}).get("test"),
            "lint_command": data.get("scripts", {}).get("lint"),
            "build_command": data.get("scripts", {}).get("build"),
        }
    except Exception as e:
        logger.warning(f"Failed to parse package.json: {e}")
        return {}


def parse_composer_json(file_path: str | Path) -> dict[str, Any]:
    """Parse composer.json for scripts, dependencies, and metadata."""
    try:
        content = Path(file_path).read_text(encoding="utf-8")
        data = json.loads(content)

        scripts = data.get("scripts", {})

        return {
            "name": data.get("name", ""),
            "scripts": scripts,
            "require": list(data.get("require", {}).keys()),
            "require-dev": list(data.get("require-dev", {}).keys()),
            "test_command": scripts.get("test") or scripts.get("phpunit"),
            "lint_command": scripts.get("lint") or scripts.get("phpstan"),
            "autoload": data.get("autoload", {}),
        }
    except Exception as e:
        logger.warning(f"Failed to parse composer.json: {e}")
        return {}


def parse_pyproject_toml(file_path: str | Path) -> dict[str, Any]:
    """Parse pyproject.toml for project metadata and scripts."""
    try:
        content = Path(file_path).read_bytes()
        data = tomllib.loads(content.decode("utf-8"))

        project = data.get("project", {})
        tool = data.get("tool", {})

        # Extract scripts from various tools
        scripts = {}

        # Poetry scripts
        if "poetry" in tool:
            scripts.update(tool["poetry"].get("scripts", {}))

        # Hatch scripts
        if "hatch" in tool:
            scripts.update(tool["hatch"].get("envs", {}).get("default", {}).get("scripts", {}))

        # PDM scripts
        if "pdm" in tool:
            scripts.update(tool["pdm"].get("scripts", {}))

        return {
            "name": project.get("name", ""),
            "version": project.get("version", ""),
            "scripts": scripts,
            "dependencies": project.get("dependencies", []),
            "dev_dependencies": project.get("optional-dependencies", {}).get("dev", []),
            "test_command": scripts.get("test", "pytest"),
            "lint_command": scripts.get("lint", "ruff check ."),
        }
    except Exception as e:
        logger.warning(f"Failed to parse pyproject.toml: {e}")
        return {}


def parse_go_mod(file_path: str | Path) -> dict[str, Any]:
    """Parse go.mod for module info."""
    try:
        content = Path(file_path).read_text(encoding="utf-8")

        module_match = None
        deps = []

        for line in content.splitlines():
            if line.startswith("module "):
                module_match = line.replace("module ", "").strip()
            elif line.strip().startswith("require"):
                # Parse require block
                continue
            elif line.strip() and not line.startswith("//"):
                parts = line.strip().split()
                if len(parts) >= 1:
                    deps.append(parts[0])

        return {
            "name": module_match or "",
            "dependencies": deps,
            "test_command": "go test ./...",
            "lint_command": "go vet ./...",
        }
    except Exception as e:
        logger.warning(f"Failed to parse go.mod: {e}")
        return {}


def parse_cargo_toml(file_path: str | Path) -> dict[str, Any]:
    """Parse Cargo.toml for project metadata."""
    try:
        content = Path(file_path).read_bytes()
        data = tomllib.loads(content.decode("utf-8"))

        package = data.get("package", {})

        return {
            "name": package.get("name", ""),
            "version": package.get("version", ""),
            "dependencies": list(data.get("dependencies", {}).keys()),
            "dev_dependencies": list(data.get("dev-dependencies", {}).keys()),
            "test_command": "cargo test",
            "lint_command": "cargo clippy",
        }
    except Exception as e:
        logger.warning(f"Failed to parse Cargo.toml: {e}")
        return {}


@lru_cache(maxsize=128)
def get_project_manifest(project_path: str | Path) -> dict[str, Any]:
    """Detect and parse the appropriate manifest file for a project.
    
    Returns dict with:
        - name: project name
        - language: detected language
        - scripts: available scripts
        - test_command: command to run tests
        - lint_command: command to run linter
        - dependencies: list of dependencies
    """
    path = Path(project_path)
    # Convert to string for stable cache key if needed, or Path hash is fine
    # Path objects are hashable.

    result = {
        "name": path.name,
        "language": None,
        "scripts": {},
        "test_command": None,
        "lint_command": None,
        "dependencies": []
    }

    # Check each manifest type in priority order
    if (path / "package.json").exists():
        data = parse_package_json(path / "package.json")
        result["language"] = "typescript" if (path / "tsconfig.json").exists() else "javascript"
        result.update(data)
        # Prepend npm run for script commands
        if result.get("test_command"):
            result["test_command"] = "npm run test"
        if result.get("lint_command"):
            result["lint_command"] = "npm run lint"

    elif (path / "composer.json").exists():
        data = parse_composer_json(path / "composer.json")
        result["language"] = "php"
        result.update(data)
        if data.get("test_command"):
            result["test_command"] = f"composer run {data['test_command']}" if not data["test_command"].startswith("vendor/") else data["test_command"]

    elif (path / "pyproject.toml").exists():
        data = parse_pyproject_toml(path / "pyproject.toml")
        result["language"] = "python"
        result.update(data)

    elif (path / "go.mod").exists():
        data = parse_go_mod(path / "go.mod")
        result["language"] = "go"
        result.update(data)

    elif (path / "Cargo.toml").exists():
        data = parse_cargo_toml(path / "Cargo.toml")
        result["language"] = "rust"
        result.update(data)

    return result


def format_manifest_for_context(manifest: dict[str, Any]) -> str:
    """Format manifest info for LLM context."""
    parts = [f"## Project: {manifest.get('name', 'Unknown')}\n"]
    parts.append(f"**Language**: {manifest.get('language', 'Unknown')}\n")

    if manifest.get("test_command"):
        parts.append(f"**Test Command**: `{manifest['test_command']}`\n")

    if manifest.get("lint_command"):
        parts.append(f"**Lint Command**: `{manifest['lint_command']}`\n")

    scripts = manifest.get("scripts", {})
    if scripts:
        parts.append("\n### Available Scripts\n")
        for name, cmd in list(scripts.items())[:10]:
            parts.append(f"- `{name}`: {cmd}\n")

    deps = manifest.get("dependencies", [])
    if deps:
        parts.append(f"\n### Dependencies ({len(deps)})\n")
        parts.append(", ".join(deps[:20]))
        if len(deps) > 20:
            parts.append(f" ... and {len(deps) - 20} more")
        parts.append("\n")

    return "".join(parts)
