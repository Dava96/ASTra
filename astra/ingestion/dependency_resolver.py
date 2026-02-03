"""Dependency resolver for different languages."""

import logging
import re

from astra.interfaces.vector_store import ASTNode

logger = logging.getLogger(__name__)

class DependencyResolver:
    """Resolves dependencies (imports) between files."""

    def __init__(self):
        self._file_map = {}  # Resolvable path -> Actual file path

    def index_files(self, nodes: list[ASTNode]) -> None:
        """Build an index of file paths for resolution."""
        unique_files = {n.file_path for n in nodes}

        for f in unique_files:
            # Map "x/y/z.py" to itself
            self._file_map[f] = f

            # Map "x.y.z" format for Python
            if f.endswith(".py"):
                # astra/core/orchestrator.py -> astra.core.orchestrator
                f_norm = f.replace("\\", "/")
                py_mod = f_norm.replace("/", ".")[:-3]
                self._file_map[py_mod] = f

                # astra/core/__init__.py -> astra.core
                if py_mod.endswith(".__init__"):
                    pkg_mod = py_mod[:-9]
                    self._file_map[pkg_mod] = f

    def resolve(self, nodes: list[ASTNode]) -> list[tuple[str, str]]:
        """Resolve imports to file dependencies.

        Returns:
            List of (source_file, target_file) tuples.
        """
        dependencies = []

        # Build index first
        self.index_files(nodes)

        for node in nodes:
            if node.language == "python" and node.type in ["import_statement", "import_from_statement"]:
                deps = self._resolve_python_import(node)
                for target in deps:
                    dependencies.append((node.file_path, target))

        return dependencies

    def _resolve_python_import(self, node: ASTNode) -> list[str]:
        """Resolve a Python import node to target files.

        Handles:
        - Absolute imports: `import a.b`, `from a.b import c`
        - Relative imports: `from . import a`, `from ..module import b`
        - Package-level imports: `astra.core` -> `astra/core/__init__.py`
        """
        targets = []
        content = node.content

        # 1. Extract base module and specific names
        # We use a more robust regex that covers both 'import' and 'from ... import'
        # but the core logic is now more defensive about what it treats as a module.

        modules_to_check = []

        if node.type == "import_from_statement":
            # from [dots][module.path] import [name]
            # Match dots and module path separately
            match = re.search(r"from\s+([\. ]*)([\w\.]*)\s+import", content)
            if match:
                dots = match.group(1).replace(" ", "")
                module_path = match.group(2)

                # Resolve base module (from dots and path)
                level = len(dots) if dots else 0
                resolved_base = self._resolve_relative_module(node.file_path, module_path, level) if dots else module_path

                if resolved_base:
                    modules_to_check.append(resolved_base)

                # Also try matching specific imported names as submodules
                import_part = content.split("import")[-1]
                names = [n.strip().split(" as ")[0] for n in import_part.split(",")]
                for name in names:
                    if resolved_base:
                        modules_to_check.append(f"{resolved_base}.{name}")
                    elif dots: # from . import name
                        actual_base = self._resolve_relative_module(node.file_path, "", level)
                        if actual_base:
                             modules_to_check.append(f"{actual_base}.{name}")

        elif node.type == "import_statement":
            # import a.b, c.d as e
            clean = content.replace("import ", "")
            parts = clean.split(",")
            for p in parts:
                mod = p.strip().split(" as ")[0]
                modules_to_check.append(mod)

        # 2. Resolve modules to files using index
        for mod in modules_to_check:
            if not mod:
                continue

            # Exact match (file or module string)
            if mod in self._file_map:
                targets.append(self._file_map[mod])
                continue

            # Heuristic: check if it's a package (mod.name)
            # This is already handled during indexing in index_files

        return list(set(targets))

    def _resolve_relative_module(self, current_file: str, module_path: str, level: int) -> str | None:
        """Resolve a relative module path (e.g. ..utils) base on current file."""
        # Normalize current file path
        f_norm = current_file.replace("\\", "/")
        path_parts = f_norm.split("/")

        # Level 1 = same dir, Level 2 = parent dir, etc.
        # astra/core/orchestrator.py (3 parts: astra, core, orchestrator.py)
        # . -> astra/core
        # .. -> astra

        if len(path_parts) <= level:
            return None # Outside root

        # Parent directory components
        base_parts = path_parts[:-(level)]

        # Reconstruct dot-path
        base_mod = ".".join(base_parts)
        if module_path:
            return f"{base_mod}.{module_path}"
        return base_mod
