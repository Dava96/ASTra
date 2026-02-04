"""Custom tool loader for user-defined tools via YAML with O(1) caching."""

import logging
from pathlib import Path
from typing import Any

import yaml

from astra.core.tools import BaseTool, Tool
from astra.tools.shell import ShellExecutor

logger = logging.getLogger(__name__)


class ShellCommandTool(BaseTool):
    """Tool that executes a shell command with security checks."""

    def __init__(self, name: str, description: str, command: str, parameters: dict):
        self.name = name
        self.description = description
        self.parameters = parameters
        self._command_template = command
        self._shell = ShellExecutor()

    async def execute(self, **kwargs: Any) -> str:
        """Execute the shell command with parameter substitution."""
        # Substitute parameters in command template
        command = self._command_template
        for key, value in kwargs.items():
            # Basic sanitization for substituted values (prevent naive injection)
            safe_value = str(value).replace(";", "").replace("&", "").replace("|", "")
            command = command.replace(f"{{{key}}}", safe_value)

        # Use ShellExecutor for execution (enforces allowlist)
        logger.info(f"Executing custom tool '{self.name}': {command}")

        result = await self._shell.run_string_async(command)

        if result.success:
            return result.stdout or "Command completed successfully"
        else:
            return f"Error (exit {result.return_code}):\n{result.stderr or result.message or 'Unknown error'}"


class CustomToolLoader:
    """Loader for custom tools with O(1) caching."""

    def __init__(self):
        self._cache: dict[str, tuple[float, list[Tool]]] = {}

    def load_tools(self, tools_dir: str | Path) -> list[Tool]:
        """Load tools with caching based on directory mtime."""
        path = Path(tools_dir)
        if not path.exists():
            return []

        try:
            # Get current mtime of the directory
            current_mtime = path.stat().st_mtime

            # Check cache
            str_path = str(path.absolute())
            if str_path in self._cache:
                last_mtime, cached_tools = self._cache[str_path]
                if last_mtime == current_mtime:
                    logger.debug(f"Cache hit for custom tools in {path}")
                    return cached_tools

            # Cache miss or stale
            logger.info(f"Loading custom tools from {path} (Cache miss)")
            tools = self._scan_directory(path)
            self._cache[str_path] = (current_mtime, tools)
            return tools

        except Exception as e:
            logger.error(f"Failed to load custom tools: {e}")
            return []

    def _scan_directory(self, path: Path) -> list[Tool]:
        tools = []
        for yaml_file in path.glob("*.yaml"):
            try:
                tool = self._load_single_tool(yaml_file)
                if tool:
                    tools.append(tool)
            except Exception as e:
                logger.error(f"Error loading {yaml_file}: {e}")
        return tools

    def _load_single_tool(self, yaml_file: Path) -> Tool | None:
        spec = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))

        # Validation
        if not isinstance(spec, dict):
            return None

        required = ["name", "description", "command"]
        if not all(k in spec for k in required):
            logger.warning(f"Skipping {yaml_file}: Missing required fields {required}")
            return None

        # Build schema
        params_schema = {"type": "object", "properties": {}, "required": []}

        if "parameters" in spec and isinstance(spec["parameters"], dict):
            for param_name, param_spec in spec["parameters"].items():
                if not isinstance(param_spec, dict):
                    continue
                params_schema["properties"][param_name] = {
                    "type": param_spec.get("type", "string"),
                    "description": param_spec.get("description", ""),
                }
                if param_spec.get("required", False):
                    params_schema["required"].append(param_name)

        return ShellCommandTool(
            name=spec["name"],
            description=spec["description"],
            command=spec["command"],
            parameters=params_schema,
        )

    def validate_tool_definition(self, yaml_content: str) -> list[str]:
        """Validate YAML content without loading."""
        errors = []
        try:
            spec = yaml.safe_load(yaml_content)
            if not isinstance(spec, dict):
                return ["Root must be a dictionary"]

            for field in ["name", "description", "command"]:
                if field not in spec:
                    errors.append(f"Missing field: {field}")

            # Simple command injection check on template (heuristic)
            if ";" in spec.get("command", "") or "&&" in spec.get("command", ""):
                errors.append("Warning: Command contains shell sequencing characters (; or &&)")

        except yaml.YAMLError as e:
            errors.append(f"YAML Parse Error: {e}")

        return errors


# Singleton instance
_loader = CustomToolLoader()


def load_custom_tools(tools_dir: str | Path) -> list[Tool]:
    """Public API for loading tools."""
    return _loader.load_tools(tools_dir)


def validate_tool_file(path: str | Path) -> list[str]:
    """Validate a specific tool file."""
    try:
        content = Path(path).read_text(encoding="utf-8")
        return _loader.validate_tool_definition(content)
    except Exception as e:
        return [str(e)]


# Default location for custom tools
DEFAULT_CUSTOM_TOOLS_DIR = Path("./tools/custom")
