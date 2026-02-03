
import asyncio
from unittest.mock import MagicMock, patch

from astra.core.context import ContextGatherer
from astra.core.tools import ToolRegistry


async def verify():
    print("Starting verification...")

    # Setup Mocks
    vector_store = MagicMock()
    tools = ToolRegistry()
    gatherer = ContextGatherer(vector_store, tools)

    # Mock Manifests
    with patch('astra.core.context.get_manifest_files_for_project') as mock_manifest:
        mock_manifest.return_value = {"huge_file.txt": "A" * 1000}

        # Mock Architecture
        with patch('pathlib.Path.read_text') as mock_read:
            mock_read.return_value = "B" * 10000

            # Mock Vector Content
            # 10 items of 2000 chars each = 20000 chars
            mock_node = MagicMock()
            mock_node.node.file_path = "test.py"
            mock_node.node.start_line = 1
            mock_node.node.content = "C" * 2000
            gatherer._vector_store.query.return_value = [mock_node] * 10

            # Mock KG
            gatherer._tools.get = MagicMock(return_value=None)

            # Run
            result = await gatherer.gather("q", "c", "p")

            print(f"Result Length: {len(result)}")
            if len(result) < 26000:
                print("PASS: Length within limit")
            else:
                print(f"FAIL: Length {len(result)} exceeds limit")

            if "truncated" in result:
                print("PASS: Truncation marker found")
            else:
                print("FAIL: Truncation marker NOT found")
                # Print tail to see what happened
                print(f"Tail: {result[-200:]}")

if __name__ == "__main__":
    asyncio.run(verify())
