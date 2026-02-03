import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock

from astra.config import get_config
from astra.core.orchestrator import Orchestrator
from astra.core.task_queue import TaskQueue
from astra.handlers.command_handlers import CommandHandler
from astra.interfaces.gateway import Command


async def verify():
    print("🚀 Starting Ingestion Robustness Verification...")

    config = get_config()
    gateway = MagicMock()
    # Mock send_followup to print messages
    async def mock_send_followup(interaction, message, **kwargs):
        print(f"📡 Gateway Followup: {message}")
    gateway.send_followup = mock_send_followup

    # Mock send_message for status updates
    async def mock_send_message(message):
        print(f"📦 Gateway Message: {message.content}")
    gateway.send_message = mock_send_message

    orchestrator = Orchestrator(gateway=gateway, config=config)
    queue = TaskQueue()
    handler = CommandHandler(gateway=gateway, orchestrator=orchestrator, queue=queue, config=config)

    # Mock Safeguard to bypass network/system checks
    from astra.core.safeguard import Safeguard
    safeguard_mock = MagicMock(spec=Safeguard)
    safeguard_mock.check_repo_size.return_value = (True, "Mocked Safe")
    safeguard_mock.check_system_resources.return_value = (True, "Mocked Safe")

    # Patch the Safeguard class in command_handlers
    import astra.handlers.command_handlers as ch
    ch.Safeguard = lambda: safeguard_mock

    repo_url = "https://github.com/google-deepmind/ASTra"
    repo_name = "ASTra"
    dest = f"./repos/{repo_name}"

    # Test 1: Project Switching (Skip Clone)
    print("\n--- Test 1: Project Switching (Skip Clone) ---")
    if not os.path.exists(dest):
        os.makedirs(dest, exist_ok=True)
        # Create a dummy .git to simulate existing repo
        os.makedirs(os.path.join(dest, ".git"), exist_ok=True)

    cmd = Command(
        user_id="test_user",
        channel_id="test_channel",
        name="checkout",
        args={"request": repo_url},
        raw_interaction=MagicMock()
    )

    response = await handler.handle_checkout(cmd)
    print(f"📥 Handler Response: {response}")

    # Test 2: Background Ingestion & Project Isolation
    print("\n--- Test 2: Background Ingestion & Project Isolation ---")
    # Wait for background task (we need to find it)
    # Since we can't easily wait for a random task, let's wait a few seconds
    print("⏳ Waiting for background ingestion to start/finish...")
    await asyncio.sleep(10) # 10s should be enough for a few nodes in this environment

    kg_path = f"./data/projects/{repo_name}/knowledge_graph.graphml"
    if os.path.exists(kg_path):
        print(f"✅ SUCCESS: Project-specific Knowledge Graph found at {kg_path}")
        size = os.path.getsize(kg_path)
        print(f"📊 KG Size: {size} bytes")
    else:
        print(f"❌ FAILURE: Knowledge Graph not found at {kg_path}")
        # List data dir
        print("📁 Data directory contents:")
        for p in Path("./data").rglob("*"):
            print(f"  - {p}")

    # Test 3: Batch processing (Check logs if possible, or just size)
    # We'll just check if the process didn't crash
    print("\n--- Test 3: Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(verify())
