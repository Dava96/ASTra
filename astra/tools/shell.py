"""Shell command executor with allowlist and async support."""

import asyncio
import logging
import os
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from astra.config import get_config
from astra.core.tools import BaseTool

logger = logging.getLogger(__name__)


@dataclass
class ShellResult:
    """Result of a shell command execution."""
    success: bool
    stdout: str
    stderr: str
    return_code: int
    command: list[str]
    blocked: bool = False
    message: str | None = None


class ShellExecutor(BaseTool):
    """Execute shell commands with allowlist enforcement and async support."""

    name = "shell_execute"
    description = "Execute shell commands within the project environment. Requires command allowlisting."
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute"
            },
            "cwd": {
                "type": "string",
                "description": "Current working directory for the command"
            }
        },
        "required": ["command"]
    }

    def __init__(
        self,
        on_blocked: Callable[[str, list[str]], None] | None = None,
        timeout: int = 300
    ):
        self._config = get_config()
        self._on_blocked = on_blocked
        self._timeout = timeout

    def _is_allowed(self, command: list[str]) -> tuple[bool, str | None]:
        """Check if a command is allowed by the configuration."""
        if not command:
            return False, "Empty command"

        binary = command[0]
        if not self._config.is_command_allowed(binary):
            logger.warning(f"BLOCKED: {binary} not in allowlist. Command: {' '.join(command)}")
            if self._on_blocked:
                self._on_blocked(binary, command)
            return False, f"Command '{binary}' is not permitted. Add via `/config allowlist add {binary}` to permit."

        return True, None

    def run(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None
    ) -> ShellResult:
        """Execute a shell command synchronously (Blocking)."""
        allowed, error_msg = self._is_allowed(command)
        if not allowed:
            return ShellResult(
                success=False,
                stdout="",
                stderr=error_msg or "Blocked",
                return_code=-1,
                command=command,
                blocked=True,
                message=error_msg
            )

        effective_timeout = timeout or self._timeout
        logger.debug(f"Executing (sync): {' '.join(command)}")

        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=effective_timeout
            )
            return ShellResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
                command=command
            )
        except subprocess.TimeoutExpired:
            return ShellResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {effective_timeout}s",
                return_code=-1,
                command=command,
                message="Consider increasing timeout."
            )
        except Exception as e:
            return ShellResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                command=command
            )

    async def run_async(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None
    ) -> ShellResult:
        """Execute a shell command asynchronously (Non-blocking) with output capping."""
        allowed, error_msg = self._is_allowed(command)
        if not allowed:
            return ShellResult(
                success=False,
                stdout="",
                stderr=error_msg or "Blocked",
                return_code=-1,
                command=command,
                blocked=True,
                message=error_msg
            )

        effective_timeout = timeout or self._timeout
        MAX_OUTPUT_BYTES = 10 * 1024 * 1024  # 10MB limit

        logger.debug(f"Executing (async): {' '.join(command)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env or os.environ.copy()
            )

            stdout_lines = []
            stderr_lines = []
            total_bytes = 0

            async def read_stream(stream, lines: list):
                nonlocal total_bytes
                while True:
                    if total_bytes >= MAX_OUTPUT_BYTES:
                         if not lines or lines[-1] != "[... Output Truncated ...]":
                             lines.append("[... Output Truncated ...]")
                         # Drain remaining silently
                         while await stream.readline(): pass
                         break

                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode('utf-8', errors='replace').rstrip()
                    lines.append(decoded)
                    total_bytes += len(line)

            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(process.stdout, stdout_lines),
                        read_stream(process.stderr, stderr_lines)
                    ),
                    timeout=effective_timeout
                )
                await process.wait()
            except TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
                return ShellResult(
                    success=False,
                    stdout="\n".join(stdout_lines),
                    stderr=f"Command timed out after {effective_timeout}s",
                    return_code=-1,
                    command=command
                )

            return ShellResult(
                success=process.returncode == 0,
                stdout="\n".join(stdout_lines),
                stderr="\n".join(stderr_lines),
                return_code=process.returncode or 0,
                command=command
            )

        except Exception as e:
            logger.error(f"Async execution failed: {e}")
            return ShellResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                command=command
            )

    def run_string(self, command_string: str, **kwargs) -> ShellResult:
        """Parse string and run synchronously."""
        try:
            command = shlex.split(command_string)
            return self.run(command, **kwargs)
        except ValueError as e:
            return ShellResult(False, "", f"Parse error: {e}", -1, [command_string], blocked=True)

    async def run_string_async(self, command_string: str, **kwargs) -> ShellResult:
        """Parse string and run asynchronously."""
        try:
            command = shlex.split(command_string)
            return await self.run_async(command, **kwargs)
        except ValueError as e:
            return ShellResult(False, "", f"Parse error: {e}", -1, [command_string], blocked=True)

    async def execute(self, command: str, cwd: str | None = None, **kwargs: Any) -> Any:
        """Tool entry point - executes asynchronously."""
        result = await self.run_string_async(command, cwd=cwd)
        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "code": result.return_code,
            "blocked": result.blocked,
            "message": result.message
        }
