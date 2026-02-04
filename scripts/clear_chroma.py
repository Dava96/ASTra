import sys

from astra.adapters.chromadb_store import ChromaDBStore


def clear_collection(name):
    store = ChromaDBStore()
    try:
        store._client.delete_collection(name)
        print(f"✅ Collection '{name}' deleted.")
    except Exception as e:
        print(f"ℹ️ Could not delete collection '{name}': {e}")


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "ASTra"
    clear_collection(name)
