import logging
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tree_sitter import Parser, Query
from tree_sitter_language_pack import get_language, get_parser

logger = logging.getLogger(__name__)

@dataclass
class ASTNode:
    id: str
    type: str
    name: str
    content: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    metadata: dict[str, Any] = field(default_factory=dict)

# Mapping of file extensions to tree-sitter languages
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
}

# Manifest files that can help with context
LANGUAGE_MANIFEST_FILES = {
    "python": ["pyproject.toml", "requirements.txt", "setup.py"],
    "javascript": ["package.json"],
    "typescript": ["package.json", "tsconfig.json"],
    "tsx": ["package.json", "tsconfig.json"],
    "rust": ["Cargo.toml"],
    "go": ["go.mod", "go.sum"],
    "java": ["pom.xml", "build.gradle"],
    "php": ["composer.json", "composer.lock"],
    "ruby": ["Gemfile"],
}

# Node types to extract as significant code items (fallback manual walk)
EXTRACTABLE_NODES = {
    "python": ["class_definition", "function_definition", "decorated_definition"],
    "javascript": ["class_declaration", "function_declaration", "method_definition", "variable_declarator"],
    "typescript": ["class_declaration", "function_declaration", "method_definition", "interface_declaration", "type_alias_declaration"],
    "tsx": ["class_declaration", "function_declaration", "method_definition", "interface_declaration", "type_alias_declaration"],
    "rust": ["struct_item", "enum_item", "function_item", "impl_item", "trait_item"],
    "go": ["type_declaration", "function_declaration", "method_declaration"],
    "java": ["class_declaration", "interface_declaration", "method_declaration", "enum_declaration"],
    "php": ["class_declaration", "function_declaration", "method_declaration", "interface_declaration"],
    "ruby": ["class", "method", "module"],
}

# Tree-sitter queries for high-performance node extraction
# Level 1: Signatures (Classes, Functions)
# Level 2: +Metadata (Decorators, Docstrings) - often covered by Level 1 nodes but can be explicit
# Level 3: Full (Variables, Imports, Nested items)
LANGUAGE_QUERIES = {
    "python": {
        1: """
            (class_definition name: (identifier) @name) @node
            (function_definition name: (identifier) @name) @node
            (decorated_definition definition: [
                (class_definition name: (identifier) @name)
                (function_definition name: (identifier) @name)
            ]) @node
        """,
        3: """
            (import_statement) @node
            (import_from_statement) @node
            (assignment left: (identifier) @name) @node
        """
    },
    "javascript": {
        1: """
            (class_declaration name: (identifier) @name) @node
            (function_declaration name: (identifier) @name) @node
            (method_definition name: (property_identifier) @name) @node
        """,
        3: """
            (import_statement) @node
            (variable_declarator name: (identifier) @name) @node
        """
    },
    "typescript": {
        1: """
            (class_declaration name: (type_identifier) @name) @node
            (function_declaration name: (identifier) @name) @node
            (method_definition name: (property_identifier) @name) @node
            (interface_declaration name: (type_identifier) @name) @node
            (type_alias_declaration name: (type_identifier) @name) @node
        """,
        3: """
            (import_statement) @node
            (variable_declarator name: (identifier) @name) @node
        """
    },
    "tsx": {
        1: """
            (class_declaration name: (type_identifier) @name) @node
            (function_declaration name: (identifier) @name) @node
            (method_definition name: (property_identifier) @name) @node
            (interface_declaration name: (type_identifier) @name) @node
            (type_alias_declaration name: (type_identifier) @name) @node
        """,
        3: """
            (import_statement) @node
            (variable_declarator name: (identifier) @name) @node
        """
    },
    "rust": {
        1: """
            (function_item name: (identifier) @name) @node
            (impl_item type: (type_identifier) @name) @node
            (struct_item name: (type_identifier) @name) @node
            (enum_item name: (type_identifier) @name) @node
            (trait_item name: (identifier) @name) @node
        """,
        3: """
            (use_declaration) @node
            (let_declaration pattern: (identifier) @name) @node
        """
    },
    "go": {
        1: """
            (function_declaration name: (identifier) @name) @node
            (method_declaration name: (identifier) @name) @node
            (type_declaration (type_spec name: (type_identifier) @name)) @node
        """,
        3: """
            (import_declaration) @node
            (var_declaration (var_spec name: (identifier) @name)) @node
            (short_var_declaration left: (expression_list (identifier) @name)) @node
        """
    },
}


def get_language_for_file(filepath: str | Path) -> str | None:
    """Get the tree-sitter language for a file."""
    ext = Path(filepath).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext)


def get_manifest_files_for_project(project_path: str | Path) -> dict[str, str]:
    """Detect project languages and return existing manifest files with contents."""
    project_path = Path(project_path)
    manifests = {}

    detected_languages = set()
    for ext, lang in EXTENSION_TO_LANGUAGE.items():
        if list(project_path.rglob(f"*{ext}"))[:1]:
            detected_languages.add(lang)

    seen_files = set()
    for lang in detected_languages:
        for manifest in LANGUAGE_MANIFEST_FILES.get(lang, []):
            if manifest in seen_files:
                continue
            seen_files.add(manifest)

            manifest_path = project_path / manifest
            if manifest_path.exists():
                try:
                    content = manifest_path.read_text(encoding="utf-8")[:4000]
                    manifests[manifest] = content
                except Exception as e:
                    logger.warning(f"Failed to read {manifest}: {e}")

    return manifests


def extract_node_name(node, language: str, captures: dict = None) -> str:
    """Extract a human-readable name for an AST node."""
    name_node = None

    if captures and isinstance(captures, dict):
        if "name" in captures:
            name_node = captures["name"]
        elif 1 in captures:
            name_node = captures[1]

    if name_node:
        try:
            return name_node.text.decode("utf-8", errors="replace")
        except Exception:
            pass

    if language in ["typescript", "tsx", "javascript"]:
        for child in node.children:
            if child.type == "identifier":
                name_node = child
                break
            if child.type == "variable_declarator":
                for sub in child.children:
                    if sub.type == "identifier":
                        name_node = sub
                        break

    elif language == "python":
        for child in node.children:
            if child.type == "identifier":
                name_node = child
                break

    elif language == "php":
        for child in node.children:
            if child.type == "name":
                name_node = child
                break

    elif language in ["rust", "go"]:
        for child in node.children:
            if child.type == "identifier":
                name_node = child
                break

    if name_node:
        return name_node.text.decode("utf-8", errors="replace")

    return "anonymous"


class ASTParser:
    """Orchestrates multi-language AST parsing using tree-sitter."""

    def __init__(self):
        self._languages = {}
        self._parsers = {}
        self._queries = {}

    def _get_parser(self, language: str) -> Parser | None:
        if language not in self._parsers:
            try:
                lang_obj = get_language(language)
                parser = get_parser(language)
                self._languages[language] = lang_obj
                self._parsers[language] = parser
            except Exception as e:
                logger.error(f"Failed to load parser for {language}: {e}")
                return None
        return self._parsers[language]

    def _get_query(self, language: str, depth: int = 3) -> Query | None:
        cache_key = (language, depth)
        if cache_key not in self._queries:
            lang_queries = LANGUAGE_QUERIES.get(language, {})
            if not lang_queries:
                return None

            # Construct query based on depth
            # Level 1 always included
            query_parts = [lang_queries.get(1, "")]
            # Level 2 is currently metadata, we might add explicit queries later
            # Level 3 adds more detail
            if depth >= 3:
                query_parts.append(lang_queries.get(3, ""))

            query_str = "\n".join(query_parts).strip()
            if not query_str:
                return None

            try:
                lang_obj = self._languages.get(language) or get_language(language)
                self._queries[cache_key] = lang_obj.query(query_str)
            except Exception as e:
                logger.error(f"Failed to load query for {language} (depth {depth}): {e}")
                return None
        return self._queries[cache_key]

    def parse_file(self, filepath: str | Path, relative_to: str | Path | None = None, ast_depth: int = 3) -> list[ASTNode]:
        """Parse a file and extract AST nodes."""
        import traceback
        filepath = Path(filepath)
        language = get_language_for_file(filepath)
        if not language:
            return []

        parser = self._get_parser(language)
        if not parser:
            return []

        try:
            content = filepath.read_bytes()
            tree = parser.parse(content)
        except Exception as e:
            logger.error(f"Failed to parse {filepath}: {e}")
            return []

        rel_path = filepath.relative_to(relative_to) if relative_to else filepath
        nodes = []
        query = self._get_query(language, ast_depth)

        node_matches = []
        if query:
            try:
                # ... (existing capture handling)
                # captures() can return various formats depending on version
                captures_list = query.captures(tree.root_node)

                # ...
                # (I'll keep the existing code but add a print after matching)

                # If it's a dictionary, the keys are tag names
                if isinstance(captures_list, dict):
                    nodes_list = captures_list.get("node", [])
                    names_list = captures_list.get("name", [])
                    for i, node_cap in enumerate(nodes_list):
                        caps = {"node": node_cap}
                        if i < len(names_list):
                            caps["name"] = names_list[i]
                        node_matches.append((node_cap, caps))
                else:
                    # If it's a list, it's (node, tag)
                    current_node = None
                    current_caps = {}
                    for item in captures_list:
                        try:
                            if len(item) == 2:
                                node_cap, tag = item
                            elif len(item) == 3:
                                node_cap, tag, _ = item
                            else:
                                continue

                            tag_name = str(tag)
                            if tag_name == "node":
                                if current_node:
                                    node_matches.append((current_node, current_caps))
                                current_node = node_cap
                                current_caps = {"node": node_cap}
                            elif tag_name == "name":
                                current_caps["name"] = node_cap
                        except Exception:
                            continue
                    if current_node:
                        node_matches.append((current_node, current_caps))
            except Exception as e:
                logger.debug(f"Query extraction failed for {filepath}: {e}")
                query = None # Fallback to manual walk

        if not query:
            # Fallback for languages without queries or if query failed
            target_types = []
            if ast_depth >= 1:
                target_types.extend(EXTRACTABLE_NODES.get(language, []))

            def walk(node, depth=0):
                if node.type in target_types:
                    node_matches.append((node, {}))
                for child in node.children:
                    walk(child, depth + 1)
            walk(tree.root_node)

        for node_cap, caps in node_matches:
            try:
                name = extract_node_name(node_cap, language, caps)
                content_text = node_cap.text.decode("utf-8", errors="replace")

                node_id = f"{rel_path}:{node_cap.type}:{name}:{node_cap.start_point[0]}:{node_cap.start_point[1]}:{node_cap.end_point[0]}:{node_cap.end_point[1]}"

                ast_node = ASTNode(
                    id=node_id,
                    type=node_cap.type,
                    name=name,
                    content=content_text,
                    file_path=str(rel_path),
                    start_line=node_cap.start_point[0] + 1,
                    end_line=node_cap.end_point[0] + 1,
                    language=language,
                    metadata={"column": node_cap.start_point[1]}
                )
                nodes.append(ast_node)
            except Exception:
                logger.error(f"Error processing node in {filepath}: {traceback.format_exc()}")
                continue

        logger.debug(f"Parsed {filepath}: {len(nodes)} nodes")
        return nodes

    def parse_directory(
        self,
        directory: str | Path,
        ignore_patterns: list[str] | None = None,
        max_depth: int | None = None,
        ast_depth: int = 3,
        max_file_size_kb: int = 100,
        progress_callback: Callable[[int, int, int], None] | None = None
    ) -> Generator[ASTNode, None, None]:
        """Parse all files in a directory, yielding nodes."""
        import os
        directory = Path(directory)
        ignore_patterns = ignore_patterns or []

        valid_files = []
        for root, dirs, files in os.walk(directory):
            root_path = Path(root)

            # Handle max_depth
            if max_depth is not None:
                try:
                    depth = len(root_path.relative_to(directory).parts)
                    if depth > max_depth:
                        dirs[:] = [] # Prevent walking deeper
                        continue
                except ValueError:
                    pass

            if any(p in str(root_path) for p in [".git", "__pycache__", "node_modules", ".venv", "env"]):
                dirs[:] = []
                continue

            for file in files:
                file_path = root_path / file
                if get_language_for_file(file_path) and file_path.stat().st_size <= max_file_size_kb * 1024:
                    valid_files.append(file_path)

        total_files = len(valid_files)
        for i, file_path in enumerate(valid_files):
            try:
                yield from self.parse_file(file_path, directory, ast_depth=ast_depth)
            except Exception as e:
                logger.warning(f"Failed to parse {file_path}: {e}")

            if progress_callback:
                progress_callback(int((i + 1) / total_files * 100), i + 1, total_files)
