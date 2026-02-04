"""Full integration tests for ASTra without mocks."""

import contextlib
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Imports moved inside test to ensure patching works for modules imported at runtime


@pytest.mark.asyncio
class TestFullIntegration:
    """Integration tests for the full pipeline using temporary resources."""

    @pytest.fixture
    def temp_env(self):
        """Create a temporary environment with Windows-safe cleanup."""
        temp_dir = tempfile.mkdtemp()
        project_dir = os.path.join(temp_dir, "test_project")
        os.makedirs(project_dir)

        yield Path(temp_dir), Path(project_dir)

        # Windows often locks ChromaDB files. Attempt cleanup but don't fail test if it fails.
        import gc

        gc.collect()
        with contextlib.suppress(PermissionError, OSError):
            shutil.rmtree(temp_dir)

    async def test_ingestion_end_to_end(self, temp_env):
        """Test full ingestion, vector storage, and graph building."""
        root_dir, project_dir = temp_env

        # 1. Setup Project Files
        # main.py importing utils
        (project_dir / "main.py").write_text("import utils\n\ndef main():\n    utils.help()")

        # utils.py
        (project_dir / "utils.py").write_text("def help():\n    print('helping')")

        # .venv/ignored.py (should be skipped)
        venv_dir = project_dir / ".venv"
        venv_dir.mkdir()
        (venv_dir / "ignored.py").write_text("print('should not be indexed')")

        # 2. Configure Environment
        chroma_dir = root_dir / "chromadb"
        graph_file = root_dir / "graph.graphml"

        # Create a mock config that behaves like the real one but overrides paths
        mock_config = MagicMock()

        # Define response mapping for config.get
        def mock_get(section, key, default=None):
            mapping = {
                ("vectordb", "persist_path"): str(chroma_dir),
                ("knowledge_graph", "persist_path"): str(graph_file),
                ("ingestion", "ignore_patterns"): [".venv", "__pycache__"],
                ("ingestion", "max_file_size_kb"): 100,
                ("ingestion", "embedding_model"): "codebert",
            }
            return mapping.get((section, key), default)

        mock_config.get.side_effect = mock_get

        from astra.config import reset_config
        reset_config()

        # Patch config in all modules that might have imported it
        patch_paths = [
            "astra.config.get_config",
            "astra.ingestion.pipeline.get_config",
            "astra.ingestion.knowledge_graph.get_config",
            "astra.adapters.chromadb_store.get_config",
        ]

        with contextlib.ExitStack() as stack:
            for path in patch_paths:
                stack.enter_context(patch(path, return_value=mock_config))
            from astra.adapters.chromadb_store import ChromaDBStore
            from astra.ingestion.knowledge_graph import KnowledgeGraph
            from astra.main import run_ingestion

            # 3. Run Ingestion
            await run_ingestion(str(project_dir))

            # Debug nodes
            graph_for_debug = KnowledgeGraph(persist_path=str(graph_file))
            nodes = list(graph_for_debug._graph.nodes)
            print(f"DEBUG: Ingested nodes: {nodes}")
            print(f"DEBUG: Persist path used: {graph_for_debug._persist_path}")
            print(f"DEBUG: Graph file exists: {graph_file.exists()}")
            if graph_file.exists():
                print(f"DEBUG: Graph file size: {graph_file.stat().st_size}")

            # 4. Verification - Knowledge Graph
            assert graph_file.exists(), f"Graph file {graph_file} was not created"
            # Pass the explicit path to avoid using config default
            graph = KnowledgeGraph(persist_path=str(graph_file))

            main_file_node = "main.py"
            utils_file_node = "utils.py"

            assert graph._graph.has_node(main_file_node), f"File node {main_file_node} missing"
            assert graph._graph.has_node(utils_file_node), f"File node {utils_file_node} missing"

            # Check dependency edge (file -> file)
            assert graph._graph.has_edge(main_file_node, utils_file_node), (
                f"Dependency edge {main_file_node} -> {utils_file_node} missing"
            )

            # Verify AST node containment
            ast_nodes = [
                n
                for n, d in graph._graph.nodes(data=True)
                if d.get("file_path") == "main.py" and d.get("type") != "file"
            ]
            assert len(ast_nodes) > 0, f"No AST nodes found for main.py (found: {ast_nodes})"
            for ast_node in ast_nodes:
                assert graph._graph.has_edge(ast_node, main_file_node), (
                    f"AST node {ast_node} should be linked to {main_file_node}"
                )

            # Verify Ignore Patterns
            nodes = list(graph._graph.nodes)
            assert not any("ignored.py" in str(n) for n in nodes), (
                "Node from .venv should be ignored"
            )

            # 5. Verification - ChromaDB
            store = ChromaDBStore(persist_path=str(chroma_dir))
            collection_name = "test_project"

            results = store.query(collection_name, "help", n_results=5)
            found_utils = any("utils.py" in str(r.node.file_path) for r in results)
            assert found_utils, "Should find utils.py via semantic search"

            # 6. Verification - Context Retrieval
            deps = graph.get_file_dependencies(main_file_node)
            assert utils_file_node in deps, (
                f"Graph should return {utils_file_node} as dependency of {main_file_node}"
            )
