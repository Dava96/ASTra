from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.adapters.chromadb_store import ChromaDBStore
from astra.adapters.gateways.discord.gateway import DiscordGateway
from astra.interfaces.gateway import Message

# === Discord Gateway Tests ===


@pytest.mark.asyncio
async def test_discord_gateway_all_paths(tmp_path):
    """Surgically test DiscordGateway paths by mocking instance attributes."""
    with (
        patch("astra.adapters.gateways.discord.gateway.get_config"),
        patch("astra.adapters.gateways.discord.gateway.os.getenv", return_value="TOKEN"),
    ):
        # Instantiate with minimal noise
        with (
            patch("astra.adapters.gateways.discord.gateway.discord.Client"),
            patch("astra.adapters.gateways.discord.gateway.app_commands.CommandTree"),
        ):
            gateway = DiscordGateway()

        # Replace attributes with robust mocks
        mock_client = AsyncMock()
        mock_client.user.id = 123
        gateway._client = mock_client

        mock_tree = MagicMock()
        mock_tree.sync = AsyncMock()
        gateway._tree = mock_tree

        # 1. Test ready event logic
        # We can't easily trigger the local on_ready, so we'll test start/stop
        await gateway.start()
        mock_client.start.assert_called_with("TOKEN")

        await gateway.stop()
        mock_client.close.assert_called()

        # 2. Test send_message variants
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()

        # discord.Client.get_channel is synchronous, but mock_client is AsyncMock
        # We must ensure get_channel is a sync MagicMock
        mock_client.get_channel = MagicMock(return_value=mock_channel)

        # Long content
        await gateway.send_message(Message(channel_id="1", content="a" * 2000))
        mock_channel.send.assert_called()

        # With file
        f = tmp_path / "f.txt"
        f.touch()
        await gateway.send_message(Message(channel_id="1", content="hi", file_path=str(f)))
        assert "file" in mock_channel.send.call_args[1]

        # 3. Test progress
        await gateway.send_progress("1", 50, "doing")
        mock_channel.send.assert_called()

        # 4. Test confirmation
        mock_msg = AsyncMock()
        mock_channel.send.return_value = mock_msg

        # We must mock ConfirmationView because the real one waits for timeout
        mock_view_instance = MagicMock()
        mock_view_instance.wait = AsyncMock()  # wait() is async
        mock_view_instance.value = True

        with patch(
            "astra.adapters.gateways.discord.gateway.ConfirmationView",
            return_value=mock_view_instance,
        ):
            assert await gateway.request_confirmation("1", "ok") is True


@pytest.mark.asyncio
async def test_discord_followup_and_auth():
    """Test following and auth paths."""
    with (
        patch("astra.adapters.gateways.discord.gateway.get_config"),
        patch("astra.adapters.gateways.discord.gateway.discord.Client"),
        patch("astra.adapters.gateways.discord.gateway.app_commands.CommandTree"),
    ):
        gateway = DiscordGateway()

        # Followup
        mock_interaction = MagicMock()
        mock_interaction.followup = AsyncMock()
        await gateway.send_followup(mock_interaction, content="hi")
        mock_interaction.followup.send.assert_called()

        # Auth delegation
        gateway._auth = MagicMock()
        gateway.is_admin("1")
        gateway._auth.is_admin.assert_called()


# === ChromaDB Tests ===


class FakeCollection:
    def __init__(self, name, count=0, last_accessed=None):
        self.name = name
        self._count = count
        self.metadata = {"last_accessed": last_accessed} if last_accessed else {}

    def count(self):
        return self._count

    def upsert(self, **kwargs):
        pass

    def query(self, **kwargs):
        return {
            "ids": [["id1"]],
            "documents": [["doc"]],
            "metadatas": [[{"type": "f"}]],
            "distances": [[0.1]],
        }

    def delete(self, **kwargs):
        pass


def test_chromadb_lifecycle_robust(tmp_path):
    """Test ChromaDBStore using FakeCollection for predictable behavior."""
    with patch("chromadb.PersistentClient") as MockClient:
        store = ChromaDBStore(persist_path=str(tmp_path / "chroma_db"))

        # Mock interactions
        c1 = FakeCollection("old", count=5, last_accessed="2020-01-01T00:00:00+00:00")
        MockClient.return_value.list_collections.return_value = [c1]
        MockClient.return_value.get_or_create_collection.return_value = c1

        # Test stale cleanup
        deleted = store.cleanup_stale_collections(max_age_days=1)
        assert "old" in deleted or len(deleted) > 0

        # Test stats
        stats = store.get_collection_stats("old")
        assert stats["count"] == 5

        # Test delete nodes
        store.delete_nodes("old", ["id1"])

        # Test errors in clear
        MockClient.return_value.delete_collection.side_effect = Exception("fail")
        store.clear_collection("old")  # Should log error
