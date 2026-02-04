import asyncio
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("investigation")

# Add project root
sys.path.append(str(Path.cwd()))

from astra.core.context import ContextGatherer
from astra.core.orchestrator import ToolRegistry


async def investigate():
    project_path = r"c:\Users\David\Desktop\Projects and Ideas\Code\Antigravity\ASTra\repos\osrs-progress-lambda"
    collection_name = "osrs_progress_lambda" # Derived from project name usually
    query = "improve performance"

    print(f"Investigating Context Gathering for:\nProject: {project_path}\nQuery: {query}\nCollection: {collection_name}")

    # 1. Vector Store (Real)
    from astra.adapters.chromadb_store import ChromaDBStore
    from astra.config import get_config

    config = get_config()
    print(f"[Investigator] using DB path: {config.vectordb.persist_path}")

    vector_store = ChromaDBStore(config.vectordb.persist_path)

    # Check collection count
    try:
        coll = vector_store._client.get_collection(collection_name)
        count = coll.count()
        print(f"[ChromaDB] Collection '{collection_name}' has {count} documents.")
    except Exception as e:
        print(f"[ChromaDB] Failed to get collection '{collection_name}': {e}")

    # 2. Tools (KG)
    tools = ToolRegistry()

    # 3. Instantiate
    gatherer = ContextGatherer(vector_store=vector_store, tools=tools)

    # 4. Run Gather
    print("\n--- Running Gather (Empty Vector/KG) ---")
    context = await gatherer.gather(query, collection_name, project_path)
    print("Gathered Context Length:", len(context))
    print("Content Preview:\n" + context[:500])

    if "Architecture" not in context:
        print("\n[!] FAILURE: Architecture missing from context!")
    if "Manifests" not in context and "dependencies" not in context.lower():
         print("\n[!] FAILURE: Manifests missing from context!")

if __name__ == "__main__":
    asyncio.run(investigate())
