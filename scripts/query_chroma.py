import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path if running as script
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from astra.adapters.chromadb_store import ChromaDBStore  # noqa: E402
from astra.config import get_config  # noqa: E402
from astra.ingestion.knowledge_graph import KnowledgeGraph  # noqa: E402

# Ensure we have a basic logging config so we see CRITICAL errors
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Query AST nodes from ChromaDB.")
    parser.add_argument("files", nargs="*", help="List of file paths to query nodes for.")
    parser.add_argument("--query", "-q", help="Semantic search query string.")
    parser.add_argument(
        "--limit", "-l", type=int, default=10, help="Limit results for semantic search."
    )
    parser.add_argument("--collection", help="Override collection name.")
    parser.add_argument(
        "--context", "-c", action="store_true", help="Include related files from Knowledge Graph."
    )
    parser.add_argument(
        "--depth", type=int, default=1, help="Depth of graph traversal (default: 1)."
    )
    parser.add_argument("--raw", action="store_true", help="Print raw ChromaDB response.")

    args = parser.parse_args()

    # Defaults
    cwd = Path.cwd()
    project_root = Path(__file__).parent.parent
    collection_name = args.collection or project_root.name

    if not args.files and not args.query:
        parser.print_help()
        sys.exit(0)

    # Process file paths to match stored format (relative to CWD)
    target_files = []
    for p in args.files:
        path_obj = Path(p)
        if path_obj.is_absolute():
            try:
                rel = path_obj.relative_to(cwd)
                target_files.append(str(rel))
            except ValueError:
                target_files.append(p)
        else:
            target_files.append(str(path_obj))

    # Context Expansion via Knowledge Graph
    expansion_metadata = {}  # file_path -> reason
    final_file_list = set(target_files)

    if args.context and target_files:
        try:
            graph = KnowledgeGraph()
            current_layer = set(target_files)

            for _d in range(args.depth):
                next_layer = set()
                for file_path in current_layer:
                    deps = graph.get_file_dependencies(file_path)
                    for dep in deps:
                        if dep not in final_file_list:
                            final_file_list.add(dep)
                            next_layer.add(dep)
                            expansion_metadata[dep] = "dependency"

                    dependents = graph.get_file_dependents(file_path)
                    for dep in dependents:
                        if dep not in final_file_list:
                            final_file_list.add(dep)
                            next_layer.add(dep)
                            expansion_metadata[dep] = "dependent"
                current_layer = next_layer
                if not current_layer:
                    break
        except Exception as e:
            if not Path("./data/knowledge_graph.graphml").exists():
                print(
                    "Warning: Knowledge Graph file not found. Run scripts/generate_graph.py first for context expansion.",
                    file=sys.stderr,
                )
            else:
                print(f"Warning: Failed to load Knowledge Graph: {e}", file=sys.stderr)

    # Connect to ChromaDB with timeout/error protection
    try:
        logging.getLogger("chromadb").setLevel(logging.ERROR)

        # O(1) Pre-check: Ensure database path is accessible
        persist_path = Path(get_config().get("vectordb", "persist_path", default="./data/chromadb"))
        if not persist_path.exists():
            print(
                json.dumps({"error": "ChromaDB directory not found. Please run ingestion first."})
            )
            sys.exit(1)

        store = ChromaDBStore()

        # Safe collection listing
        raw_cols = store._client.list_collections()
        collections = []
        for c in raw_cols:
            name = c.name if hasattr(c, "name") else str(c)
            collections.append(name)

        if collection_name not in collections:
            print(
                json.dumps(
                    {"error": f"Collection '{collection_name}' not found. Available: {collections}"}
                )
            )
            sys.exit(1)

        col = store._get_collection(collection_name)
    except Exception as e:
        error_msg = str(e)
        if "InternalError" in error_msg or "hnsw" in error_msg or "deadlock" in error_msg.lower():
            print(
                json.dumps(
                    {
                        "error": f"ChromaDB Internal Error: {error_msg}",
                        "suggestion": "Your vector store index may be corrupted. Try deleting the './data/chromadb' directory and re-indexing.",
                    }
                ),
                file=sys.stderr,
            )
        else:
            print(json.dumps({"error": f"Failed to connect to ChromaDB: {e}"}), file=sys.stderr)
        sys.exit(1)

    output = []

    # Semantic Query
    if args.query:
        try:
            print(f"Searching for: '{args.query}'...", file=sys.stderr)
            results = store.query(
                collection=collection_name,
                query_text=args.query,
                n_results=args.limit,
                filter_metadata={"file_path": {"$in": list(final_file_list)}}
                if target_files
                else None,
            )
            for res in results:
                node = res.node
                output.append(
                    {
                        "id": node.id,
                        "score": round(res.score, 4),
                        "relationship": "semantic_match",
                        "metadata": node.metadata,
                        "content": node.content
                        if len(node.content) < 1000
                        else node.content[:1000] + "...",
                    }
                )
        except Exception as e:
            print(json.dumps({"error": f"Semantic query failed: {e}"}))
            sys.exit(1)

    # File-based lookup
    elif target_files:
        try:
            query_files = list(final_file_list)
            results = col.get(where={"file_path": {"$in": query_files}})  # type: ignore

            if results and results.get("ids"):
                ids = results["ids"]
                metadatas = results["metadatas"]
                documents = results["documents"]

                for i, node_id in enumerate(ids):
                    meta = metadatas[i] if metadatas else {}
                    file_path = meta.get("file_path", "")

                    relation = "target"
                    if file_path in expansion_metadata:
                        relation = expansion_metadata[file_path]

                    item = {
                        "id": node_id,
                        "relationship": relation,
                        "metadata": meta,
                        "content": documents[i] if documents else "",
                    }
                    output.append(item)
        except Exception as e:
            print(json.dumps({"error": f"Metadata query failed: {e}"}))
            sys.exit(1)

    # Print JSON
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
