"""File read/write operations with safety checks and confinement."""

import logging
import os
import shutil
from collections.abc import Generator
from pathlib import Path
from typing import Any

from astra.config import get_config
from astra.core.tools import BaseTool

logger = logging.getLogger(__name__)


class FileOps(BaseTool):
    """Safe file operations with backup support."""

    name = "file_operations"
    description = "Read, write, delete, copy, or move files within the project."
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["read", "write", "delete", "copy", "move", "exists", "list"],
                "description": "The file operation to perform"
            },
            "path": {
                "type": "string",
                "description": "Source file or directory path"
            },
            "content": {
                "type": "string",
                "description": "Content to write (for 'write' operation)"
            },
            "destination": {
                "type": "string",
                "description": "Destination path (for 'copy' or 'move' operations)"
            },
            "append": {
                "type": "boolean",
                "description": "Append to file instead of overwriting (for 'write' operation)"
            }
        },
        "required": ["operation", "path"]
    }

    def __init__(self, backup_enabled: bool = True):
        self._backup_enabled = backup_enabled
        self._config = get_config()
        self._root_dir = Path(os.getcwd()).resolve() # Default to CWD, can be overridden by config if needed
        # Check if confinement is enabled in config
        self._confinement_enabled = self._config.get("tools", "confinement", "enforce_root", default=True)

    def _validate_path(self, path: str | Path) -> Path:
        """Validate that path is within the project root."""
        abs_path = Path(path).resolve()

        if self._confinement_enabled:
            # We must be careful about case sensitivity on Windows, but resolve() handles normalization.
            if not str(abs_path).lower().startswith(str(self._root_dir).lower()):
                 # Allow temp dirs or specific exceptions if needed, but strict for now
                 raise ValueError(f"Path '{path}' is outside project root '{self._root_dir}'")

        return abs_path

    async def execute(self, operation: str, path: str, **kwargs: Any) -> Any:
        """Execute the requested file operation."""
        try:
            if operation == "read":
                content = self.read(path)
                return content if content is not None else "❌ Failed to read file."
            elif operation == "write":
                content = kwargs.get("content", "")
                append = kwargs.get("append", False)
                success = self.write(path, content, append=append)
                return "✅ File written successfully." if success else "❌ Failed to write file."
            elif operation == "delete":
                success = self.delete(path)
                return "✅ File deleted successfully." if success else "❌ Failed to delete file."
            elif operation == "copy":
                dest = kwargs.get("destination")
                if not dest: return "❌ Destination required for copy."
                success = self.copy(path, dest)
                return f"✅ Copied to {dest}." if success else "❌ Failed to copy."
            elif operation == "move":
                dest = kwargs.get("destination")
                if not dest: return "❌ Destination required for move."
                success = self.move(path, dest)
                return f"✅ Moved to {dest}." if success else "❌ Failed to move."
            elif operation == "exists":
                return self.exists(path)
            elif operation == "list":
                files = list(self.list_files(path))
                # return relative paths for cleaner output if possible
                return [
                    str(f.relative_to(self._root_dir) if f.is_relative_to(self._root_dir) else f)
                    for f in files
                ]
            else:
                return f"❌ Unknown operation: {operation}"
        except ValueError as e:
            logger.warning(f"Security violation: {e}")
            return f"❌ Security Error: {e}"
        except Exception as e:
            logger.error(f"Operation failed: {e}")
            return f"❌ Error: {e}"

    def read(self, file_path: str | Path, max_size: int = 5 * 1024 * 1024) -> str | None:
        """Read file content with size limit (Default 5MB)."""
        try:
            path = self._validate_path(file_path)
            if not path.exists():
                return None

            # Check size
            if path.stat().st_size > max_size:
                raise ValueError(f"File size ({path.stat().st_size}) exceeds limit ({max_size} bytes)")

            return path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return None

    def write(self, file_path: str | Path, content: str, backup: bool = True, append: bool = False) -> bool:
        """Write content to file with optional backup and append mode."""
        try:
            path = self._validate_path(file_path)

            # Create backup if file exists and not appending
            if backup and self._backup_enabled and path.exists() and not append:
                backup_path = path.with_suffix(path.suffix + ".bak")
                shutil.copy2(path, backup_path)

            # Ensure directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write content
            mode = "a" if append else "w"
            with path.open(mode, encoding="utf-8") as f:
                f.write(content)

            logger.debug(f"Wrote {len(content)} bytes to {file_path} (append={append})")
            return True

        except Exception as e:
            logger.error(f"Failed to write {file_path}: {e}")
            return False

    def delete(self, file_path: str | Path, backup: bool = True) -> bool:
        """Delete a file with optional backup."""
        try:
            path = self._validate_path(file_path)

            if not path.exists():
                return True

            if backup and self._backup_enabled:
                backup_path = path.with_suffix(path.suffix + ".deleted")
                shutil.move(str(path), str(backup_path))
            else:
                path.unlink()

            logger.debug(f"Deleted {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete {file_path}: {e}")
            return False

    def copy(self, src: str | Path, dst: str | Path) -> bool:
        """Copy a file."""
        try:
            src_path = self._validate_path(src)
            dst_path = self._validate_path(dst)

            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            return True
        except Exception as e:
            logger.error(f"Failed to copy {src} to {dst}: {e}")
            return False

    def move(self, src: str | Path, dst: str | Path) -> bool:
        """Move a file."""
        try:
            src_path = self._validate_path(src)
            dst_path = self._validate_path(dst)

            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_path), str(dst_path))
            return True
        except Exception as e:
            logger.error(f"Failed to move {src} to {dst}: {e}")
            return False

    def exists(self, file_path: str | Path) -> bool:
        """Check if file exists."""
        try:
            path = self._validate_path(file_path)
            return path.exists()
        except ValueError:
            return False

    def list_files(
        self,
        directory: str | Path,
        pattern: str = "*",
        recursive: bool = True,
        max_depth: int | None = None
    ) -> Generator[Path, None, None]:
        """List files in a directory."""
        dir_path = self._validate_path(directory)

        if not dir_path.is_dir():
             return

        if max_depth is not None:
            # Manual traversal for depth control
            base_depth = len(dir_path.parts)
            for path in dir_path.rglob(pattern) if recursive else dir_path.glob(pattern):
                if len(path.parts) - base_depth <= max_depth:
                    yield path
        elif recursive:
            yield from dir_path.rglob(pattern)
        else:
            yield from dir_path.glob(pattern)

    def get_size(self, file_path: str | Path) -> int:
        """Get file size in bytes."""
        try:
            path = self._validate_path(file_path)
            return path.stat().st_size
        except Exception:
            return 0

    def restore_backup(self, file_path: str | Path) -> bool:
        """Restore a file from backup."""
        try:
            path = self._validate_path(file_path)
            backup_path = path.with_suffix(path.suffix + ".bak")

            if backup_path.exists():
                shutil.copy2(backup_path, path)
                backup_path.unlink()
                logger.info(f"Restored {file_path} from backup")
                return True
        except Exception as e:
             logger.error(f"Failed to restore {file_path}: {e}")

        return False
