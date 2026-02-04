"""Tests for the DependencyResolver."""

import pytest

from astra.ingestion.dependency_resolver import DependencyResolver
from astra.interfaces.vector_store import ASTNode


@pytest.fixture
def resolver():
    return DependencyResolver()


def test_index_files(resolver):
    nodes = [
        ASTNode(
            id="n1",
            type="module",
            name="mod1",
            file_path="astra/core/orchestrator.py",
            content="",
            start_line=1,
            end_line=1,
            language="python",
        ),
        ASTNode(
            id="n2",
            type="module",
            name="mod2",
            file_path="astra/ingestion/pipeline.py",
            content="",
            start_line=1,
            end_line=1,
            language="python",
        ),
    ]
    resolver.index_files(nodes)

    # Check normalized paths
    assert "astra/core/orchestrator.py" in resolver._file_map
    assert "astra.core.orchestrator" in resolver._file_map
    assert "astra.ingestion.pipeline" in resolver._file_map


def test_resolve_absolute_imports(resolver):
    nodes = [
        ASTNode(
            id="n1",
            type="module",
            name="mod1",
            file_path="source.py",
            content="",
            start_line=1,
            end_line=1,
            language="python",
        ),
        ASTNode(
            id="n2",
            type="module",
            name="mod2",
            file_path="target.py",
            content="",
            start_line=1,
            end_line=1,
            language="python",
        ),
        ASTNode(
            id="n3",
            type="import_statement",
            name="import",
            file_path="source.py",
            content="import target",
            start_line=1,
            end_line=1,
            language="python",
        ),
    ]
    # We need n1, n2 in the index for resolution to work
    resolver.index_files(nodes)

    deps = resolver.resolve([nodes[2]])
    assert ("source.py", "target.py") in deps


def test_resolve_from_imports(resolver):
    target_node = ASTNode(
        id="n2",
        type="module",
        name="orchestrator",
        file_path="astra/core/orchestrator.py",
        content="",
        start_line=1,
        end_line=1,
        language="python",
    )
    source_node = ASTNode(
        id="n1",
        type="import_from_statement",
        name="import",
        file_path="main.py",
        content="from astra.core import orchestrator",
        start_line=1,
        end_line=1,
        language="python",
    )

    deps = resolver.resolve([source_node, target_node])
    assert ("main.py", "astra/core/orchestrator.py") in deps


def test_resolve_relative_imports(resolver):
    # current file: astra/ingestion/pipeline.py
    # import: from . import parser
    target_node = ASTNode(
        id="n2",
        type="module",
        name="parser",
        file_path="astra/ingestion/parser.py",
        content="",
        start_line=1,
        end_line=1,
        language="python",
    )
    source_node = ASTNode(
        id="n1",
        type="import_from_statement",
        name="import",
        file_path="astra/ingestion/pipeline.py",
        content="from . import parser",
        start_line=1,
        end_line=1,
        language="python",
    )

    deps = resolver.resolve([source_node, target_node])
    assert ("astra/ingestion/pipeline.py", "astra/ingestion/parser.py") in deps


def test_resolve_relative_parent_imports(resolver):
    # current file: astra/ingestion/pipeline.py
    # import: from ..core import orchestrator
    target_node = ASTNode(
        id="n2",
        type="module",
        name="orchestrator",
        file_path="astra/core/orchestrator.py",
        content="",
        start_line=1,
        end_line=1,
        language="python",
    )
    source_node = ASTNode(
        id="n1",
        type="import_from_statement",
        name="import",
        file_path="astra/ingestion/pipeline.py",
        content="from ..core import orchestrator",
        start_line=1,
        end_line=1,
        language="python",
    )

    deps = resolver.resolve([source_node, target_node])
    assert ("astra/ingestion/pipeline.py", "astra/core/orchestrator.py") in deps
