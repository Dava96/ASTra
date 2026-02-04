"""Handlers for project-related commands."""

import asyncio
import logging
from pathlib import Path

from astra.config import Config
from astra.core.clock import Clock, SystemClock
from astra.core.orchestrator import Orchestrator
from astra.core.safeguard import Safeguard
from astra.interfaces.gateway import Command, Gateway
from astra.tools.git_ops import GitHubVCS

logger = logging.getLogger(__name__)

UPDATE_INTERVAL_SECONDS = 5  # Progress update frequency


class ProjectHandlers:
    """Handles execution of project-related slash commands."""

    def __init__(
        self, gateway: Gateway, orchestrator: Orchestrator, config: Config, clock: Clock = None
    ):
        self.gateway = gateway
        self.orchestrator = orchestrator
        self.config = config
        self.clock = clock or SystemClock()

    async def handle_checkout(self, cmd: Command):
        """Handle /checkout command."""
        repo_url = cmd.args.get("repo", "") or cmd.args.get("request", "")
        if not repo_url:
            await self.gateway.send_followup(
                cmd.raw_interaction, "❌ Please provide a repository URL"
            )
            return

        # Run Safety Checks
        safeguard = Safeguard()
        safe, msg = safeguard.check_repo_size(repo_url)
        if not safe:
            await self.gateway.send_followup(cmd.raw_interaction, f"❌ Safety Limit: {msg}")
            return

        safe, msg = safeguard.check_system_resources()
        if not safe:
            await self.gateway.send_followup(cmd.raw_interaction, f"❌ System Critical: {msg}")
            return

        # Extract repo name safely
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        # Sanitize to prevent path traversal
        repo_name = Path(repo_name).name
        dest = f"./repos/{repo_name}"
        repo_dir = Path(dest)

        vcs = GitHubVCS()

        # Check if already cloned
        if repo_dir.exists() and (repo_dir / ".git").exists():
            await self.gateway.send_followup(
                cmd.raw_interaction, f"📂 Project `{repo_name}` already exists. Switching..."
            )
        else:
            await self.gateway.send_followup(cmd.raw_interaction, f"🛰️ Cloning {repo_url}...")
            result = await vcs.clone(repo_url, dest)
            if not result.success:
                await self.gateway.send_followup(
                    cmd.raw_interaction, f"❌ Clone failed: {result.error}"
                )
                return

        # Check Branch Safety
        current_branch = await vcs.get_current_branch(dest)
        safe_branches = self.config.get("ingestion", "safe_branches", default=["main", "master"])

        if current_branch not in safe_branches:
            await self.gateway.send_followup(
                cmd.raw_interaction,
                f"⚠️ Active Repo: `{repo_name}`\n"
                f"Branch `{current_branch}` is not in safe list {safe_branches}. Indexing skipped.",
            )
            self.orchestrator.set_active_project(repo_name)
            return

        # Check if already indexed
        collection_name = repo_name.replace("-", "_")
        store = self.orchestrator._vector_store
        stats = store.get_collection_stats(collection_name)

        if stats.get("count", 0) > 0:
            await self.gateway.send_followup(
                cmd.raw_interaction,
                f"✅ Project `{repo_name}` is active. Index already exists ({stats['count']} nodes).",
            )
            self.orchestrator.set_active_project(repo_name)
            return

        # Set active project
        self.orchestrator.set_active_project(repo_name)

        # Trigger background ingestion
        asyncio.create_task(self._run_background_ingestion(repo_name, dest, cmd.channel_id))

        await self.gateway.send_followup(
            cmd.raw_interaction,
            f"✅ Project `{repo_name}` is active. Background indexing started...",
        )

    async def _run_background_ingestion(self, repo_name: str, dest: str, channel_id: str):
        """Perform ingestion and graph building in the background."""
        try:
            collection = repo_name.replace("-", "_")

            # Define progress callback for pipeline
            async def on_progress(percent, current, total):
                current_time = self.clock.now()
                nonlocal last_update_time
                if (
                    current_time - last_update_time > UPDATE_INTERVAL_SECONDS
                    and channel_id
                    and hasattr(self.gateway, "send_progress")
                ):
                    await self.gateway.send_progress(
                        channel_id,
                        percent,
                        f"Indexing `{repo_name}`... ({percent}% of files parsed)",
                    )
                    last_update_time = current_time

            last_update_time = 0

            from astra.ingestion.pipeline import IngestionPipeline

            pipeline = IngestionPipeline()

            # Run the pipeline
            total_count = await pipeline.run_async(
                directory=dest, collection_name=collection, progress_callback=on_progress
            )

            msg = f"✅ Indexing complete for `{repo_name}`: {total_count} nodes."
            if channel_id:
                if hasattr(self.gateway, "send_status_update"):
                    await self.gateway.send_status_update(channel_id, msg)
                else:
                    from astra.interfaces.gateway import Message

                    await self.gateway.send_message(Message(content=msg, channel_id=channel_id))
            else:
                logger.info(msg)

        except Exception as e:
            logger.exception(f"Background ingestion failed for {repo_name}")
            if channel_id:
                try:
                    from astra.interfaces.gateway import Message

                    await self.gateway.send_message(
                        Message(
                            content=f"⚠️ Error indexing `{repo_name}`: {e}", channel_id=channel_id
                        )
                    )
                except Exception:
                    pass
