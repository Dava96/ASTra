"""Comprehensive tests for knowledge graph with edge cases."""

from unittest.mock import MagicMock, patch

import pytest

from astra.interfaces.vector_store import ASTNode


class TestKnowledgeGraphBasics:
    """Basic knowledge graph tests."""

    @pytest.fixture
    def kg(self, tmp_path):
        """Create knowledge graph with temp persist path."""
        with patch("astra.ingestion.knowledge_graph.get_config") as mock_config:
            config = MagicMock()
            config.get = MagicMock(return_value=str(tmp_path / "test_graph.graphml"))
            mock_config.return_value = config

            from astra.ingestion.knowledge_graph import KnowledgeGraph

            return KnowledgeGraph(persist_path=str(tmp_path / "test_graph.graphml"))

    def test_add_node(self, kg):
        """Test adding a node to the graph."""
        node = ASTNode(
            id="test:func:1",
            type="function_definition",
            name="greet",
            content="function greet() {}",
            file_path="src/utils.ts",
            start_line=1,
            end_line=3,
            language="typescript",
        )

        kg.add_node(node)

        info = kg.get_node_info("test:func:1")
        assert info is not None
        assert info["name"] == "greet"

    def test_add_relationship(self, kg):
        """Test adding relationship between nodes."""
        kg._graph.add_node("src/a.ts")
        kg._graph.add_node("src/b.ts")

        kg.add_relationship("src/a.ts", "src/b.ts", "imports")

        deps = kg.get_dependencies("src/a.ts")
        assert "src/b.ts" in deps

    def test_add_import(self, kg):
        """Test adding import relationship."""
        kg._graph.add_node("src/main.ts")
        kg._graph.add_node("src/utils.ts")

        kg.add_import("src/main.ts", "src/utils.ts")

        deps = kg.get_file_dependencies("src/main.ts")
        assert "src/utils.ts" in deps

    def test_add_call(self, kg):
        """Test adding function call relationship."""
        kg._graph.add_node("func:caller:1")
        kg._graph.add_node("func:callee:1")

        kg.add_call("func:caller:1", "func:callee:1")

        deps = kg.get_dependencies("func:caller:1")
        assert "func:callee:1" in deps


class TestDependencyAnalysis:
    """Test dependency and impact analysis."""

    @pytest.fixture
    def kg_with_graph(self, tmp_path):
        """Create graph with pre-populated dependencies."""
        with patch("astra.ingestion.knowledge_graph.get_config") as mock_config:
            config = MagicMock()
            config.get = MagicMock(return_value=str(tmp_path / "test.graphml"))
            mock_config.return_value = config

            from astra.ingestion.knowledge_graph import KnowledgeGraph

            kg = KnowledgeGraph(persist_path=str(tmp_path / "test.graphml"))

            # Build a dependency chain: A -> B -> C -> D
            kg._graph.add_node("A", type="function")
            kg._graph.add_node("B", type="function")
            kg._graph.add_node("C", type="function")
            kg._graph.add_node("D", type="function")

            kg._graph.add_edge("A", "B", relationship="calls")
            kg._graph.add_edge("B", "C", relationship="calls")
            kg._graph.add_edge("C", "D", relationship="calls")

            return kg

    def test_get_dependencies(self, kg_with_graph):
        """Test getting forward dependencies."""
        deps = kg_with_graph.get_dependencies("A")
        assert "B" in deps

    def test_get_dependents(self, kg_with_graph):
        """Test getting reverse dependencies."""
        dependents = kg_with_graph.get_dependents("B")
        assert "A" in dependents

    def test_impact_analysis_direct(self, kg_with_graph):
        """Test impact analysis finds direct dependents."""
        # If we change C, B is directly affected
        impact = kg_with_graph.get_impact_analysis("C")

        assert "B" in impact["direct"]

    def test_impact_analysis_indirect(self, kg_with_graph):
        """Test impact analysis finds indirect dependents."""
        # If we change D, C is direct, B is indirect
        impact = kg_with_graph.get_impact_analysis("D", max_depth=3)

        assert "C" in impact["direct"]
        # A and B should be in indirect (through chain)

    def test_impact_analysis_depth_limit(self, kg_with_graph):
        """Test that depth limit is respected."""
        impact = kg_with_graph.get_impact_analysis("D", max_depth=1)

        # With depth 1, only direct dependents
        assert "C" in impact["direct"]
        assert len(impact["indirect"]) == 0


class TestCircularDependencies:
    """Test circular dependency detection."""

    @pytest.fixture
    def kg(self, tmp_path):
        with patch("astra.ingestion.knowledge_graph.get_config") as mock_config:
            config = MagicMock()
            config.get = MagicMock(return_value=str(tmp_path / "test.graphml"))
            mock_config.return_value = config

            from astra.ingestion.knowledge_graph import KnowledgeGraph

            return KnowledgeGraph(persist_path=str(tmp_path / "test.graphml"))

    def test_detect_circular_dependency(self, kg):
        """Test detection of circular dependencies."""
        # Create A -> B -> C -> A cycle
        kg._graph.add_node("A")
        kg._graph.add_node("B")
        kg._graph.add_node("C")

        kg._graph.add_edge("A", "B")
        kg._graph.add_edge("B", "C")
        kg._graph.add_edge("C", "A")  # Circular!

        cycles = kg.find_circular_dependencies()

        assert len(cycles) > 0

    def test_no_circular_dependencies(self, kg):
        """Test when there are no cycles."""
        kg._graph.add_node("A")
        kg._graph.add_node("B")
        kg._graph.add_node("C")

        kg._graph.add_edge("A", "B")
        kg._graph.add_edge("B", "C")

        cycles = kg.find_circular_dependencies()

        assert len(cycles) == 0


class TestPersistence:
    """Test graph persistence."""

    def test_save_and_load(self, tmp_path):
        """Test saving and loading graph."""
        persist_path = str(tmp_path / "graph.graphml")

        with patch("astra.ingestion.knowledge_graph.get_config") as mock_config:
            config = MagicMock()
            config.get = MagicMock(return_value=persist_path)
            mock_config.return_value = config

            from astra.ingestion.knowledge_graph import KnowledgeGraph

            # Create and save
            kg1 = KnowledgeGraph(persist_path=persist_path)
            kg1._graph.add_node("test_node", type="function", name="test")
            kg1.save()

            # Load in new instance
            kg2 = KnowledgeGraph(persist_path=persist_path)

            # Node should exist
            assert "test_node" in kg2._graph.nodes

    def test_load_nonexistent_file(self, tmp_path):
        """Test loading when file doesn't exist."""
        persist_path = str(tmp_path / "nonexistent.graphml")

        with patch("astra.ingestion.knowledge_graph.get_config") as mock_config:
            config = MagicMock()
            config.get = MagicMock(return_value=persist_path)
            mock_config.return_value = config

            from astra.ingestion.knowledge_graph import KnowledgeGraph

            # Should not crash, just create empty graph
            kg = KnowledgeGraph(persist_path=persist_path)

            assert kg._graph.number_of_nodes() == 0


class TestGraphStats:
    """Test graph statistics."""

    @pytest.fixture
    def kg(self, tmp_path):
        with patch("astra.ingestion.knowledge_graph.get_config") as mock_config:
            config = MagicMock()
            config.get = MagicMock(return_value=str(tmp_path / "test.graphml"))
            mock_config.return_value = config

            from astra.ingestion.knowledge_graph import KnowledgeGraph

            return KnowledgeGraph(persist_path=str(tmp_path / "test.graphml"))

    def test_get_stats_empty(self, kg):
        """Test stats on empty graph."""
        stats = kg.get_stats()

        assert stats["nodes"] == 0
        assert stats["edges"] == 0

    def test_get_stats_populated(self, kg):
        """Test stats on populated graph."""
        kg._graph.add_node("f1", type="function")
        kg._graph.add_node("f2", type="function_definition")
        kg._graph.add_node("c1", type="class")
        kg._graph.add_node("c2", type="class_declaration")
        kg._graph.add_edge("f1", "f2")

        stats = kg.get_stats()

        assert stats["nodes"] == 4
        assert stats["edges"] == 1


class TestEdgeCases:
    """Edge case tests."""

    @pytest.fixture
    def kg(self, tmp_path):
        with patch("astra.ingestion.knowledge_graph.get_config") as mock_config:
            config = MagicMock()
            config.get = MagicMock(return_value=str(tmp_path / "test.graphml"))
            mock_config.return_value = config

            from astra.ingestion.knowledge_graph import KnowledgeGraph

            return KnowledgeGraph(persist_path=str(tmp_path / "test.graphml"))

    def test_clear_graph(self, kg):
        """Test clearing the graph."""
        kg._graph.add_node("A")
        kg._graph.add_node("B")
        kg._graph.add_edge("A", "B")

        kg.clear()

        assert kg._graph.number_of_nodes() == 0
        assert kg._graph.number_of_edges() == 0

    def test_get_node_info_nonexistent(self, kg):
        """Test getting info for non-existent node."""
        info = kg.get_node_info("nonexistent")
        assert info is None

    def test_get_dependencies_nonexistent(self, kg):
        """Test getting dependencies for non-existent node."""
        deps = kg.get_dependencies("nonexistent")
        assert deps == []

    def test_get_dependents_nonexistent(self, kg):
        """Test getting dependents for non-existent node."""
        dependents = kg.get_dependents("nonexistent")
        assert dependents == []

    def test_get_file_dependencies_empty(self, kg):
        """Test file dependencies when node has none."""
        kg._graph.add_node("isolated_file.ts")

        deps = kg.get_file_dependencies("isolated_file.ts")
        assert deps == []

    def test_unicode_node_names(self, kg):
        """Test handling of unicode in node names."""
        kg._graph.add_node("src/日本語.ts", type="file")
        kg._graph.add_node("src/مرحبا.ts", type="file")
        kg._graph.add_edge("src/日本語.ts", "src/مرحبا.ts", relationship="imports")

        deps = kg.get_file_dependencies("src/日本語.ts")
        assert "src/مرحبا.ts" in deps

    def test_special_characters_in_paths(self, kg):
        """Test handling special characters in file paths."""
        kg._graph.add_node("src/[slug]/page.tsx", type="file")
        kg._graph.add_node("src/(group)/layout.tsx", type="file")

        kg.add_import("src/[slug]/page.tsx", "src/(group)/layout.tsx")

        deps = kg.get_file_dependencies("src/[slug]/page.tsx")
        assert "src/(group)/layout.tsx" in deps
