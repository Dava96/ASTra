"""Main entry point for ASTra."""

import asyncio
import logging
import os
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = typer.Typer()


# Setup logging
def setup_logging(cli_mode: bool = False):
    """Configure application logging."""
    from astra.config import get_config

    config = get_config()

    log_path = config.orchestration.log_path
    log_dir = Path(log_path).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    handlers = [logging.FileHandler(log_path)]

    # In CLI mode, we don't want logs polluting stdout unless verbose
    if not cli_mode:
        handlers.append(logging.StreamHandler(sys.stdout))

    from pythonjsonlogger import jsonlogger

    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z"
    )

    for handler in handlers:
        handler.setFormatter(formatter)

    logging.basicConfig(level=logging.INFO, handlers=handlers)

    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)


async def start_discord_bot():
    """Start the Discord bot."""
    setup_logging(cli_mode=False)
    logger = logging.getLogger(__name__)

    logger.info("Starting ASTra...")

    from astra.adapters.gateways.discord import DiscordGateway
    from astra.config import get_config
    from astra.core.orchestrator import Orchestrator
    from astra.core.task_queue import TaskQueue

    config = get_config()

    if not os.getenv("DISCORD_TOKEN"):
        print("\n⚠️  DISCORD_TOKEN not set!")
        sys.exit(1)

    gateway = DiscordGateway(config)
    queue = TaskQueue()
    orchestrator = Orchestrator(gateway, config, task_queue=queue)

    # Wire up direct chat
    gateway.set_chat_handler(orchestrator.chat)

    # Register commands
    from astra.handlers.command_handlers import CommandHandler

    cmd_handler = CommandHandler(gateway, orchestrator, queue, config)

    gateway.register_built_in_commands(
        on_feature=cmd_handler.handle_feature,
        on_fix=cmd_handler.handle_fix,
        on_quick=cmd_handler.handle_quick,
        on_checkout=cmd_handler.handle_checkout,
        on_status=cmd_handler.handle_status,
        on_cancel=cmd_handler.handle_cancel,
        on_last=cmd_handler.handle_last,
        on_approve=cmd_handler.handle_approve,
        on_revise=cmd_handler.handle_revise,
        on_screenshot=cmd_handler.handle_screenshot,
        on_history=cmd_handler.handle_history,
        on_docker=cmd_handler.handle_docker,
        on_cron=cmd_handler.handle_cron,
        on_web=cmd_handler.handle_web,
        on_cleanup=cmd_handler.handle_cleanup,
        on_model=cmd_handler.handle_model,
        on_auth=cmd_handler.handle_auth,
        on_health=cmd_handler.handle_health,
        on_tools=cmd_handler.handle_tools,
        on_config=cmd_handler.handle_config,
    )

    asyncio.create_task(orchestrator.start())

    async def broadcast_ready():
        # Wait a bit for gateway to connect
        await asyncio.sleep(5)
        await gateway.broadcast("✅ **System Ready!** ASTra is online and indexing is complete.")

    logger.info("ASTra is ready!")
    asyncio.create_task(broadcast_ready())
    await gateway.start()



async def start_web_ui():
    """Start the Open WebUI Gateway."""
    setup_logging(cli_mode=False)
    logger = logging.getLogger(__name__)

    from astra.adapters.gateways.open_webui import OpenWebUIGateway
    from astra.config import get_config
    from astra.core.orchestrator import Orchestrator
    from astra.core.task_queue import TaskQueue

    config = get_config()
    logger.info("Starting ASTra Web Gateway...")

    # Initialize Gateway
    # Initialize Gateway
    gateway = OpenWebUIGateway(config)
    queue = TaskQueue()
    orchestrator = Orchestrator(gateway, config, task_queue=queue)

    # Register Commands
    from astra.handlers.command_handlers import CommandHandler

    cmd_handler = CommandHandler(gateway, orchestrator, queue, config)

    gateway.register_built_in_commands(
        on_feature=cmd_handler.handle_feature,
        on_fix=cmd_handler.handle_fix,
        on_quick=cmd_handler.handle_quick,
        on_checkout=cmd_handler.handle_checkout,
        on_status=cmd_handler.handle_status,
        on_cancel=cmd_handler.handle_cancel,
        on_last=cmd_handler.handle_last,
        on_approve=cmd_handler.handle_approve,
        on_revise=cmd_handler.handle_revise,
        on_screenshot=cmd_handler.handle_screenshot,
        on_history=cmd_handler.handle_history,
        on_docker=cmd_handler.handle_docker,
        on_cron=cmd_handler.handle_cron,
        on_web=cmd_handler.handle_web,
        on_cleanup=cmd_handler.handle_cleanup,
        on_model=cmd_handler.handle_model,
        on_auth=cmd_handler.handle_auth,
        on_health=cmd_handler.handle_health,
        on_tools=cmd_handler.handle_tools,
        on_config=cmd_handler.handle_config,
    )

    # Start Orchestrator
    asyncio.create_task(orchestrator.start())

    # Start Web Server
    await gateway.start()

    # Keep alive
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        await gateway.stop()


async def run_cli_task(prompt: str, task_type: str):
    """Run a single task via CLI."""
    setup_logging(cli_mode=True)

    from astra.adapters.gateways.console import ConsoleGateway
    from astra.config import get_config
    from astra.core.orchestrator import Orchestrator
    from astra.core.task_queue import TaskQueue

    config = get_config()
    gateway = ConsoleGateway(config)
    queue = TaskQueue()
    orchestrator = Orchestrator(gateway, config, task_queue=queue)

    # Start orchestrator logic loop
    asyncio.create_task(orchestrator.start())

    # Add task
    print(f"🚀 Starting task: {prompt}")
    task = queue.add(
        task_type=task_type,
        request=prompt,
        user_id="cli_user",
        channel_id="console",
        project=os.getcwd(),
    )

    # Wait for task completion
    # In a real event loop, we'd wait for orchestrator to process it.
    # Since orchestrator.start() is running, we just need to poll or wait for event.
    # Orchestrator doesn't have a "wait for task" method exposed easily?
    # We can poll queue status.

    while True:
        t = queue.get(task.id)
        if t.status.value in ["completed", "failed", "cancelled"]:
            print(f"\nTask finished with status: {t.status.value}")
            if t.result:
                print(f"Result: {t.result}")
            if t.error:
                print(f"Error: {t.error}")
            break
        await asyncio.sleep(1)


async def run_ingestion(path: str, max_depth: int | None = None, ast_depth: int | None = None):
    """Run ingestion for a project directory using the unified pipeline."""
    setup_logging(cli_mode=True)
    logger = logging.getLogger(__name__)

    from tqdm import tqdm

    from astra.ingestion.pipeline import IngestionPipeline

    path_obj = Path(path).resolve()
    project_name = path_obj.name
    collection_name = project_name.replace("-", "_").replace(" ", "_")

    logger.info(f"🚀 Ingesting project: {project_name} at {path_obj}")

    pipeline = IngestionPipeline()

    # Setup progress bar
    pbar = None

    async def on_progress(percent, current, total):
        nonlocal pbar
        if pbar is None:
            pbar = tqdm(total=total, desc="Ingesting", unit="file")

        # update() increments, so we need to track delta or just set?
        # tqdm.update(n) adds n.
        # We get absolute 'current'.
        # Easier to just set n, or manually calculate delta.
        # Let's calculate delta.
        if pbar.n < current:
            pbar.update(current - pbar.n)

        if current >= total:
            pbar.close()

    try:
        total_count = await pipeline.run_async(
            directory=path_obj,
            collection_name=collection_name,
            progress_callback=on_progress,
            max_depth=max_depth,
            ast_depth=ast_depth,
        )
        print(f"✅ Ingestion complete! Total nodes: {total_count}")

    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        print(f"❌ Ingestion failed: {e}")


@app.command()
def run():
    """Start the ASTra Discord Bot."""
    asyncio.run(start_discord_bot())


@app.command()
def task(prompt: str, type: str = "feature"):
    """Execute a single task directly."""
    asyncio.run(run_cli_task(prompt, type))


@app.command()
def ingest(
    path: str = typer.Argument(".", help="Project path"),
    depth: int | None = typer.Option(None, help="Max recursion depth"),
    ast_depth: int | None = typer.Option(
        None, "--ast-depth", help="AST parsing granularity (1=Signatures, 3=Full)"
    ),
):
    """Ingest a project directory (AST + Knowledge Graph)."""
    asyncio.run(run_ingestion(path, depth, ast_depth))


@app.command()
def estimate_size(
    path: str = typer.Argument(".", help="Project path"),
    sample_rate: float = typer.Option(0.05, help="Sampling rate (0.05 = 5%)"),
    ast_depth: int = typer.Option(3, help="AST granularity"),
):
    """Estimate ingestion size and DB growth."""
    from astra.ingestion.size_estimator import SizeEstimator

    estimator = SizeEstimator()
    print(
        f"📊 Estimating size for {path} (Depth: {ast_depth}, Sample: {int(sample_rate * 100)}%)..."
    )

    result = estimator.estimate(path, sample_rate, ast_depth)

    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return

    print("\n-------------------------------------------")
    print(f"📁 Total Files:       {result['total_files']}")
    print(f"💾 Total Code Size:   {result['total_size_mb']} MB")
    print(f"🧪 Sampled Files:     {result['sample_size']} ({result['sample_nodes']} nodes)")
    print(f"📏 Density:           {result['nodes_per_kb']} nodes/KB")
    print("-------------------------------------------")
    print(f"🔮 Projected Nodes:   {result['projected_nodes']}")
    print(f"💽 Est. DB Size:      {result['projected_db_size_mb']} MB")
    print("-------------------------------------------")


@app.command()
def cleanup(days: int = 30):
    """Cleanup stale collections."""
    from astra.adapters.chromadb_store import ChromaDBStore

    store = ChromaDBStore()
    store.cleanup_stale_collections(days)


@app.command()
def web():
    """Start the ASTra Web Gateway (OpenAI compatible)."""
    asyncio.run(start_web_ui())


@app.command()
def setup():
    """Run the interactive setup wizard."""
    from astra.setup_wizard import run_setup_wizard

    run_setup_wizard()


if __name__ == "__main__":
    app()
