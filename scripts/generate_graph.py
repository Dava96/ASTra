import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from astra.ingestion.dependency_resolver import DependencyResolver
from astra.ingestion.knowledge_graph import KnowledgeGraph
from astra.ingestion.parser import ASTParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    project_root = Path(__file__).parent.parent
    logger.info(f"Scanning project: {project_root}")

    parser = ASTParser()
    kg = KnowledgeGraph(persist_path="./data/knowledge_graph.graphml")
    resolver = DependencyResolver()

    # Clear existing to start fresh
    kg.clear()

    logger.info("Parsing directory...")
    # Use a list to allow batch processing
    nodes = []

    # Simple progress tracking
    def print_progress(percent, current, total):
        sys.stdout.write(f"\rParsing Files: {percent}% [{current}/{total}]")
        sys.stdout.flush()

    nodes_iterator = parser.parse_directory(
        directory=project_root,
        ignore_patterns=[
            ".venv",
            "__pycache__",
            ".git",
            "node_modules",
            "data",
            "htmlcov",
            "tmp",
            ".gemini",
        ],
        max_file_size_kb=500,
        progress_callback=print_progress,
    )

    nodes = list(nodes_iterator)
    print(f"\nAdding {len(nodes)} nodes to Knowledge Graph...")
    kg.add_nodes(nodes)

    logger.info("Resolving dependencies...")
    dependencies = resolver.resolve(nodes)
    for source, target in dependencies:
        kg.add_import(source, target)
    logger.info(f"Added {len(dependencies)} import relationships.")

    # Save the graph
    kg.save()

    stats = kg.get_stats()
    print("\n--- Knowledge Graph Generated ---")
    print(f"Total Nodes: {stats['nodes']}")
    print(f"Total Edges: {stats['edges']}")
    print(f"Files: {stats['files']}")
    print(f"Functions: {stats['functions']}")
    print(f"Classes: {stats['classes']}")
    print(f"Graph saved to: {kg._persist_path}")


if __name__ == "__main__":
    main()
