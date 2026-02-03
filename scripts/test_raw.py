
from astra.adapters.chromadb_store import ChromaDBStore


def test():
    print("Initializing store...")
    store = ChromaDBStore()
    print("Listing collections...")
    cols = store.list_collections()
    print(f"Collections: {cols}")

    if cols:
        name = cols[0]["name"]
        print(f"Querying collection: {name}")
        # Use a simple text query
        results = store.query(name, "test", n_results=1)
        print(f"Results: {results}")

if __name__ == "__main__":
    test()
