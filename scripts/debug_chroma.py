import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

# Try to disable telemetry via environment variable before importing chromadb
os.environ["ANONYMIZED_TELEMETRY"] = "False"

import chromadb
from chromadb.config import Settings


def test_init():
    print("Testing ChromaDB initialization...")
    try:
        # 1. Silencing the loggers explicitly
        for logger_name in ["chromadb.telemetry", "posthog"]:
            temp_logger = logging.getLogger(logger_name)
            temp_logger.setLevel(logging.CRITICAL)
            temp_logger.propagate = False

        # 2. Initialize client with telemetry disabled
        client = chromadb.PersistentClient(
            path="./data/chromadb", settings=Settings(anonymized_telemetry=False)
        )
        print("Client initialized successfully.")

        # 3. Try to list collections
        cols = client.list_collections()
        print(f"Found {len(cols)} collections.")

    except Exception as e:
        print(f"Initialization failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_init()
