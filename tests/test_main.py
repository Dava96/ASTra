from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from astra.main import app, setup_logging

runner = CliRunner()


def test_setup_logging(tmp_path):
    log_file = tmp_path / "astra.log"
    with patch("astra.config.get_config") as mock_config:
        mock_config.return_value.orchestration.log_path = str(log_file)
        setup_logging(cli_mode=True)
        assert log_file.parent.exists()


@pytest.mark.asyncio
async def test_start_discord_bot():
    with (
        patch("astra.adapters.gateways.discord.DiscordGateway") as mock_gateway,
        patch("astra.core.orchestrator.Orchestrator") as mock_orch,
        patch("astra.core.task_queue.TaskQueue"),
        patch("astra.handlers.command_handlers.CommandHandler"),
        patch("os.getenv", return_value="fake_token"),
    ):
        # Mock start methods
        mock_orch_inst = mock_orch.return_value
        mock_orch_inst.start = AsyncMock()
        mock_gateway_inst = mock_gateway.return_value
        mock_gateway_inst.start = AsyncMock()

        from astra.main import start_discord_bot

        await start_discord_bot()

        mock_gateway_inst.register_built_in_commands.assert_called()
        mock_gateway_inst.start.assert_called()


def test_cli_run_command():
    with patch("astra.main.start_discord_bot", new_callable=AsyncMock) as mock_start:
        result = runner.invoke(app, ["run"])
        assert result.exit_code == 0
        mock_start.assert_called_once()


def test_cli_setup_command():
    with patch("astra.setup_wizard.run_setup_wizard") as mock_setup:
        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0
        mock_setup.assert_called_once()


def test_cli_ingest_command_with_depth():
    with patch("astra.main.run_ingestion", new_callable=AsyncMock) as mock_ingest:
        result = runner.invoke(app, ["ingest", ".", "--depth", "3"])
        assert result.exit_code == 0
        mock_ingest.assert_called_once_with(".", 3, None)


def test_cli_cleanup_command():
    with patch("astra.adapters.chromadb_store.ChromaDBStore") as mock_store_cls:
        result = runner.invoke(app, ["cleanup", "--days", "60"])
        assert result.exit_code == 0

        mock_store = mock_store_cls.return_value
        mock_store.cleanup_stale_collections.assert_called_once_with(60)


@pytest.mark.asyncio
async def test_run_cli_task():
    from astra.main import run_cli_task

    with (
        patch("astra.core.orchestrator.Orchestrator") as mock_orch,
        patch("astra.core.task_queue.TaskQueue") as mock_queue,
    ):
        mock_orch_inst = mock_orch.return_value
        mock_orch_inst.start = AsyncMock()

        mock_queue_inst = mock_queue.return_value
        mock_task = MagicMock()
        mock_task.id = "t1"
        mock_task.status.value = "completed"
        mock_task.result = {"ok": True}
        mock_task.error = None

        mock_queue_inst.add.return_value = mock_task
        mock_queue_inst.get.return_value = mock_task

        await run_cli_task("test prompt", "feature")
        mock_queue_inst.add.assert_called_once()
