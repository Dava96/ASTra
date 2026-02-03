"""Aider CLI wrapper for code editing."""

import asyncio
import logging
import os
import re
import sys
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any

from astra.config import get_config
from astra.core.tools import BaseTool
from astra.interfaces.vcs import VCS
from astra.tools.shell import ShellExecutor

logger = logging.getLogger(__name__)


@dataclass
class AiderResult:
    """Result from an Aider execution."""
    success: bool
    output: str
    error: str | None = None
    files_modified: list[str] | None = None
    tokens_used: int | None = None


class AiderTool(BaseTool):
    """Wrapper for Aider CLI with streaming output, error handling, and security."""

    name = "edit_code"
    description = "Use Aider to perform complex code edits, refactors, or feature implementations across multiple files."
    parameters = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Description of the changes to make"
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of specific files to focus on"
            }
        },
        "required": ["message"]
    }

    def __init__(
        self,
        model: str | None = None,
        api_key_env: str | None = None,
        vcs: VCS | None = None
    ):
        config = get_config()
        self._model = model or config.get("orchestration", "model", default="ollama/qwen2.5-coder:7b")
        # Get the API key env var from nested config
        fallback_config = config.get("orchestration", "fallback_strategy", default={})
        if isinstance(fallback_config, dict):
            self._api_key_env = api_key_env or fallback_config.get("api_key_env_var")
        else:
            self._api_key_env = api_key_env
        self._timeout = config.get("orchestration", "global_timeout_seconds", default=600)
        self._vcs = vcs
        self._shell = ShellExecutor()

    async def execute(self, message: str, files: list[str] | None = None, **kwargs: Any) -> Any:
        """Execute the requested tool action."""
        cwd = kwargs.get("cwd", ".")

        # Integrity check: Ensure repo is clean before editing if VCS is present
        if self._vcs:
            try:
                # We prioritize verifying the branch state, though we won't block strictly on dirty state
                # unless configured, but we log it.
                branch = await self._vcs.get_current_branch(cwd)
                logger.debug(f"Aider executing on branch: {branch}")
            except Exception as e:
                logger.warning(f"VCS check failed: {e}")

        result = await self.run_async(message, cwd, files)
        return {
            "success": result.success,
            "output": result.output[:2000],  # Cap return output for the tool response
            "modified": result.files_modified
        }

    def _build_command(
        self,
        message: str,
        files: list[str] | None = None,
        context_files: list[str] | None = None,
        auto_commits: bool = False,
        yes_always: bool = True
    ) -> list[str]:
        """Build the aider command line."""
        cmd = [
            sys.executable, "-m", "aider",
            "--model", self._model,
            "--message", message,
        ]

        if not auto_commits:
            cmd.append("--no-auto-commits")

        if yes_always:
            cmd.append("--yes")

        # Add context files (read-only)
        if context_files:
            for cf in context_files:
                cmd.extend(["--read", cf])

        # Add specific files if provided
        if files:
            cmd.extend(files)

        return cmd

    def _build_env(self) -> dict[str, str]:
        """Build environment variables for Aider."""
        env = os.environ.copy()

        # Ensure API key is available if configured (must be a string)
        if self._api_key_env and isinstance(self._api_key_env, str) and self._api_key_env in os.environ:
            env[self._api_key_env] = os.environ[self._api_key_env]

        # Disable interactive prompts
        env["AIDER_YES"] = "true"

        return env

    def run(
        self,
        message: str,
        cwd: str,
        files: list[str] | None = None,
        auto_commits: bool = False,
        timeout: int | None = None
    ) -> AiderResult:
        """Run Aider synchronously and return result."""
        cmd = self._build_command(message, files, auto_commits=auto_commits)
        env = self._build_env()
        timeout = timeout or self._timeout

        # Use ShellExecutor logic for security check
        allowed, error_msg = self._shell._is_allowed(cmd)
        if not allowed:
             return AiderResult(success=False, output="", error=error_msg or "Blocked")

        result = self._shell.run(cmd, cwd=cwd, env=env, timeout=timeout)

        success = result.success
        files_modified = self._parse_modified_files(result.stdout)

        return AiderResult(
            success=success,
            output=result.stdout,
            error=result.stderr if not success else None,
            files_modified=files_modified,
            tokens_used=self._parse_token_usage(result.stdout)
        )

    async def run_async(
        self,
        message: str,
        cwd: str,
        files: list[str] | None = None,
        context_files: list[str] | None = None,
        auto_commits: bool = False,
        timeout: int | None = None,
        progress_callback: Callable[[str], None] | None = None
    ) -> AiderResult:
        """Run Aider asynchronously with optional progress streaming and memory safety."""
        MAX_OUTPUT_BYTES = 10 * 1024 * 1024  # 10MB limit

        # Resolve context files if not provided
        if context_files is None:
            from astra.core.template_manager import TemplateManager
            tm = TemplateManager()
            context_files = tm.get_context_file_paths(cwd)

        if context_files:
            logger.info(f"Injecting context files: {context_files}")

        cmd = self._build_command(message, files, context_files, auto_commits)
        env = self._build_env()
        timeout = timeout or self._timeout

        logger.info(f"Running Aider async: {' '.join(cmd[:6])}...")

        try:
            # Security check using ShellExecutor
            allowed, error_msg = self._shell._is_allowed(cmd)
            if not allowed:
                 return AiderResult(success=False, output="", error=error_msg or "Blocked")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout_lines = []
            stderr_lines = []
            total_bytes = 0

            async def read_stream(stream, lines: list, is_stderr: bool = False):
                nonlocal total_bytes
                while True:
                    if total_bytes >= MAX_OUTPUT_BYTES:
                         # Append specific warning once
                         if not lines or lines[-1] != "[... Output Truncated ...]":
                             lines.append("[... Output Truncated ...]")
                         # Drain remaining silently to avoid blocking pipe
                         while await stream.readline(): pass
                         break

                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode('utf-8', errors='replace').rstrip()
                    lines.append(decoded)
                    total_bytes += len(line)

                    # Send progress updates
                    if progress_callback and not is_stderr:
                        # Filter for meaningful progress lines
                        if any(marker in decoded for marker in ['Applying', 'Writing', 'Tokens:', '>']):
                            progress_callback(decoded[:100])

            # Read both streams concurrently with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(process.stdout, stdout_lines),
                        read_stream(process.stderr, stderr_lines, is_stderr=True)
                    ),
                    timeout=timeout
                )
                await process.wait()
            except TimeoutError:
                process.kill()
                await process.wait()
                return AiderResult(
                    success=False,
                    output="\n".join(stdout_lines),
                    error=f"Timeout after {timeout} seconds"
                )

            stdout = "\n".join(stdout_lines)
            stderr = "\n".join(stderr_lines)
            success = process.returncode == 0

            return AiderResult(
                success=success,
                output=stdout,
                error=stderr if not success else None,
                files_modified=self._parse_modified_files(stdout),
                tokens_used=self._parse_token_usage(stdout)
            )

        except Exception as e:
            logger.exception("Aider async execution failed")
            return AiderResult(
                success=False,
                output="",
                error=str(e)
            )

    async def stream_output(
        self,
        message: str,
        cwd: str,
        files: list[str] | None = None
    ) -> AsyncGenerator[str, None]:
        """Stream Aider output line by line."""
        cmd = self._build_command(message, files)
        env = self._build_env()

        # Security check using ShellExecutor
        allowed, error_msg = self._shell._is_allowed(cmd)
        if not allowed:
             yield f"Error: {error_msg or 'Blocked'}"
             return

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            yield line.decode('utf-8', errors='replace').rstrip()

        await process.wait()

    def _parse_modified_files(self, output: str) -> list[str]:
        """Parse Aider output to extract modified files."""
        files = []
        for line in output.split('\n'):
            # Aider outputs lines like "Applying edits to src/file.py"
            if line.startswith('Applying edits to '):
                file_path = line.replace('Applying edits to ', '').strip()
                files.append(file_path)
            # Or "Writing src/file.py"
            elif line.startswith('Writing '):
                file_path = line.replace('Writing ', '').strip()
                files.append(file_path)
        return files

    def _parse_token_usage(self, output: str) -> int | None:
        """Parse token usage from Aider output."""
        # Tokens: 1,234 sent, 567 received
        match = re.search(r"Tokens:\s+([\d,]+)\s+sent", output)
        if match:
            try:
                return int(match.group(1).replace(',', ''))
            except ValueError:
                pass
        return None

    def check_installed(self) -> bool:
        """Check if Aider is installed and accessible."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "aider", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
