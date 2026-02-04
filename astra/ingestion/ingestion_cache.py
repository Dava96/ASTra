import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from astra.config import get_config

logger = logging.getLogger(__name__)


class IngestionCache:
    """
    Persistent cache to track file states and support delta ingestion.
    Mapping: file_path -> content_hash
    """

    def __init__(self, persist_path: str | None = None):
        get_config()
        self._persist_path = Path(persist_path or "./data/ingestion_cache.json")
        self._cache: dict[str, dict[str, Any]] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        """Load cache from disk."""
        if self._persist_path.exists():
            try:
                text = self._persist_path.read_text(encoding="utf-8")
                raw_cache = json.loads(text)

                # Migrate old format (str -> dict) if necessary
                self._cache = {}
                for k, v in raw_cache.items():
                    if isinstance(v, str):
                        self._cache[k] = {"hash": v, "mtime": 0, "size": 0}
                    else:
                        self._cache[k] = v

                logger.debug(f"Loaded ingestion cache: {len(self._cache)} entries")
            except Exception as e:
                logger.warning(f"Failed to load ingestion cache: {e}")
                self._cache = {}

    def save(self) -> None:
        """Persist cache to disk."""
        if not self._dirty:
            return

        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = json.dumps(self._cache, indent=2)
            self._persist_path.write_text(text, encoding="utf-8")
            self._dirty = False
            logger.debug(f"Saved ingestion cache: {len(self._cache)} entries")
        except Exception as e:
            logger.error(f"Failed to save ingestion cache: {e}")

    def get_hash(self, file_path: str | Path) -> str | None:
        """Get the cached hash for a file."""
        entry = self._cache.get(str(file_path))
        return entry.get("hash") if entry else None

    def check_file(self, file_path: Path) -> bool:
        """
        Check if file matches cache based on mtime and size.
        Returns True if cache hit (file unchanged), False otherwise.
        """
        key = str(file_path)
        entry = self._cache.get(key)
        if not entry:
            return False

        try:
            stat = file_path.stat()
            # We allow a small tolerance for float comparison, though mtime is usually exact
            if (
                entry.get("size") == stat.st_size
                and abs(entry.get("mtime", 0) - stat.st_mtime) < 0.0001
            ):
                return True
        except Exception:
            pass

        return False

    def update(self, file_path: str | Path, content_hash: str) -> None:
        """Update the hash and metadata for a file."""
        key = str(file_path)
        path_obj = Path(file_path)

        try:
            stat = path_obj.stat()
            mtime = stat.st_mtime
            size = stat.st_size
        except Exception:
            mtime = 0
            size = 0

        new_entry = {"hash": content_hash, "mtime": mtime, "size": size}

        # Check if actually changed to avoid setting dirty flag unnecessarily
        current = self._cache.get(key)
        if current != new_entry:
            self._cache[key] = new_entry
            self._dirty = True

    def remove(self, file_path: str | Path) -> None:
        """Remove a file from the cache."""
        key = str(file_path)
        if key in self._cache:
            del self._cache[key]
            self._dirty = True

    @staticmethod
    def calculate_hash(file_path: Path) -> str | None:
        """Calculate SHA256 hash of a file's content."""
        try:
            # We open in binary mode
            content = file_path.read_bytes()
            return hashlib.sha256(content).hexdigest()
        except Exception:
            return None
