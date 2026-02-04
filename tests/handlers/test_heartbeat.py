from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Stable test using Clock injection


class MockClock:
    def __init__(self):
        self._time = 0.0

    def now(self) -> float:
        self._time += 100.0  # Fast fwd time on every check
        return self._time


@pytest.mark.asyncio
async def test_heartbeat_sends_updates():
    """Test using dependency injection for clock."""

    # Needs to mock sys.modules to avoid importing real BrowserTool which might crash or be slow
    with patch.dict(
        "sys.modules",
        {
            "astra.tools.browser": MagicMock(),
            "astra.tools.browser.BrowserTool": MagicMock(),
        },
    ):
        from astra.handlers.command_handlers import CommandHandler

        # Mocks
        mock_gateway = MagicMock()
        mock_gateway.send_progress = AsyncMock()
        mock_gateway.send_message = AsyncMock()
        mock_gateway.send_status_update = AsyncMock()

        mock_orchestrator = MagicMock()
        mock_orchestrator._vector_store.add_nodes = MagicMock()
        mock_orchestrator._knowledge_graph.add_node = MagicMock()
        mock_orchestrator._knowledge_graph.save = MagicMock()

        # Explicit mock parser returning list
        mock_parser = MagicMock()
        mock_parser.parse_directory.return_value = [MagicMock() for _ in range(200)]
        mock_orchestrator._parser = mock_parser

        mock_config = MagicMock()
        mock_config.get.return_value = []

        # Inject MockClock
        clock = MockClock()

        handler = CommandHandler(
            mock_gateway, mock_orchestrator, MagicMock(), mock_config, clock=clock
        )

        # Mock IngestionPipeline to simulate progress calls
        with patch("astra.ingestion.pipeline.IngestionPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value

            async def mock_run_async(directory, collection_name, progress_callback, **kwargs):
                # Call callback twice with time passing
                await progress_callback(10, 20, 200)
                await progress_callback(20, 40, 200)
                return 200

            mock_pipeline.run_async = AsyncMock(side_effect=mock_run_async)

            await handler.projects._run_background_ingestion("test_repo", ".", "channel_123")

        # Verify final success message
        # MagicMock has 'send_status_update', so the code prefers it over 'send_message'
        assert mock_gateway.send_status_update.called or mock_gateway.send_message.called
        assert mock_gateway.send_progress.call_count >= 1
