"""Handlers for system and configuration commands."""

import logging

from astra.config import Config
from astra.core.orchestrator import Orchestrator
from astra.interfaces.gateway import Command, Gateway
from astra.tools.browser import BrowserTool

logger = logging.getLogger(__name__)


class SystemHandlers:
    """Handles execution of system-related slash commands."""

    def __init__(self, gateway: Gateway, orchestrator: Orchestrator, config: Config):
        self.gateway = gateway
        self.orchestrator = orchestrator
        self.config = config

        from astra.core.monitor import Monitor

        self.monitor = Monitor()

    async def handle_config(self, cmd: Command):
        """Handle /config command."""
        print(f"DEBUG: Handling config command. Args: {cmd.args}")
        action = cmd.args.get("action", "list")
        key = cmd.args.get("key", "")
        value = cmd.args.get("value", "")
        print(f"DEBUG: Action: {action}, Key: {key}, Value: {value}")

        if action == "list":
            # Dump full config
            try:
                print("DEBUG: Dumping config model")
                config_dict = self.config.model_dump()
                print(f"DEBUG: Config dump type: {type(config_dict)}")
            except Exception as e:
                print(f"DEBUG: Failed to model_dump: {e}")
                config_dict = {}

            def flatten(d, parent_key="", sep="."):
                items = []
                for k, v in d.items():
                    new_key = f"{parent_key}{sep}{k}" if parent_key else k
                    if isinstance(v, dict):
                        items.extend(flatten(v, new_key, sep=sep).items())
                    else:
                        items.append((new_key, v))
                return dict(items)

            try:
                flat_config = flatten(config_dict)
                print(f"DEBUG: Flattened config keys: {list(flat_config.keys())[:5]}")
            except Exception as e:
                print(f"DEBUG: Flatten failed: {e}")
                flat_config = {}

            msg = "⚙️ **Full Configuration**\n\n"
            # Sort by key
            for k, v in sorted(flat_config.items()):
                msg += f"`{k}` = `{v}`\n"

            # Send via DM to avoid noise
            try:
                # Assuming raw_interaction.user.send works (verified in MFA tests)
                # Split into chunks if too long (Discord limit 2000 chars)
                lines = msg.split("\n")
                chunks = []
                current_chunk = ""
                for line in lines:
                    if len(current_chunk) + len(line) + 1 > 1900:
                        chunks.append(current_chunk)
                        current_chunk = ""
                    current_chunk += line + "\n"
                if current_chunk:
                    chunks.append(current_chunk)

                print(f"DEBUG: Sending DM chunks. Count: {len(chunks)}")
                await cmd.raw_interaction.user.send(chunks[0])
                for chunk in chunks[1:]:
                    await cmd.raw_interaction.user.send(chunk)

                print("DEBUG: Sending confirmation followup")
                await self.gateway.send_followup(cmd.raw_interaction, "✅ Sent full configuration via DM!", ephemeral=True)
            except Exception as e:
                import traceback
                traceback.print_exc()
                logger.error(f"Failed to DM config: {e}")
                await self.gateway.send_followup(cmd.raw_interaction, "❌ Failed to DM you. Ensure server DMs are enabled.", ephemeral=True)

        elif action == "get":
            print(f"DEBUG: Getting config key: {key}")
            val = self.config.get(*key.split("."))
            print(f"DEBUG: Got value: {val}")
            if val is not None:
                await self.gateway.send_followup(cmd.raw_interaction, f"ℹ️ `{key}` = `{val}`")
            else:
                 await self.gateway.send_followup(cmd.raw_interaction, f"❌ Key `{key}` not found.")

        elif action == "set":
            if not key or not value:
                 await self.gateway.send_followup(cmd.raw_interaction, "❌ Usage: /config set key=value")
                 return

            # Traverse and set
            keys = key.split(".")
            target = self.config
            try:
                # Navigate to parent
                print(f"DEBUG: Setting {key} to {value}. Navigating...")
                for k in keys[:-1]:
                     target = getattr(target, k)
                     print(f"DEBUG: Navigated to {k}, target type: {type(target)}")

                # Set value on leaf
                field_name = keys[-1]
                if not hasattr(target, field_name):
                    print(f"DEBUG: Target missing attribute {field_name}")
                    await self.gateway.send_followup(cmd.raw_interaction, f"❌ Unknown config key: `{key}`")
                    return

                # Type conversion based on existing type
                # Pydantic models have type info, but simple getattr gives value.
                # using type(getattr(...)) is basic approximation.
                current_val = getattr(target, field_name)
                target_type = type(current_val)
                print(f"DEBUG: Target field {field_name}, current type {target_type}")

                new_val = value
                if target_type is bool:
                    new_val = value.lower() in ("true", "1", "yes", "on")
                elif target_type is int:
                    new_val = int(value)
                elif target_type is float:
                    new_val = float(value)
                elif target_type is list:
                    # Simple comma split for lists
                    new_val = [x.strip() for x in value.split(",")]

                print(f"DEBUG: Setting attribute {field_name} to {new_val}")
                setattr(target, field_name, new_val)
                self.config.save()
                await self.gateway.send_followup(cmd.raw_interaction, f"✅ Set `{key}` to `{new_val}`")

            except Exception as e:
                 import traceback
                 traceback.print_exc()
                 await self.gateway.send_followup(cmd.raw_interaction, f"❌ Failed to set value: {e}")

        else:
            await self.gateway.send_followup(
                cmd.raw_interaction, "ℹ️ Use `/config list`, `/config get <key>`, or `/config set <key> <value>`"
            )

    async def handle_model(self, cmd: Command):
        """Handle /model command - change active model."""
        model = cmd.args.get("model", "")
        target = cmd.args.get("target", "planning")

        if not model:
            planning = self.config.llm.planning_model or "not set"
            coding = self.config.llm.coding_model or "same as planning"
            await self.gateway.send_followup(
                cmd.raw_interaction,
                f"ℹ️ Current Models:\n🧠 Planning: `{planning}`\n💻 Coding: `{coding}`",
            )
            return

        # Update runtime config
        if target == "coding":
            self.config.llm.coding_model = model
        else:
            self.config.llm.planning_model = model
            # For backward compatibility if needed
            self.config.llm.model = model

        # Persist to config.json
        self.config.save()

        await self.gateway.send_followup(
            cmd.raw_interaction, f"✅ {target.title()} model changed to `{model}`"
        )

    async def handle_auth(self, cmd: Command):
        """Handle /auth command - manage authorized users."""
        action = cmd.args.get("action", "list")
        user_id = cmd.args.get("user_id", "")

        if action == "list":
            allowed = self.config.orchestration.allowed_users or []
            msg = (
                "👥 **Authorized Users**\n" + "\n".join([f"• `{u}`" for u in allowed])
                if allowed
                else "No users configured"
            )
            await self.gateway.send_followup(cmd.raw_interaction, msg)
        elif action == "add" and user_id:
            if self.gateway.add_authorized_user(user_id):
                # Persistence is handled by gateway._auth calling _save_allowed_users
                await self.gateway.send_followup(cmd.raw_interaction, f"✅ Added `{user_id}`")
            else:
                await self.gateway.send_followup(
                    cmd.raw_interaction, f"ℹ️ `{user_id}` is already authorized."
                )
        elif action == "remove" and user_id:
            if self.gateway.remove_authorized_user(user_id):
                await self.gateway.send_followup(cmd.raw_interaction, f"✅ Removed `{user_id}`")
            else:
                await self.gateway.send_followup(
                    cmd.raw_interaction, f"ℹ️ `{user_id}` was not in the list."
                )
        else:
            await self.gateway.send_followup(
                cmd.raw_interaction, "Usage: /auth <list|add|remove> [user_id]"
            )

    async def handle_health(self, cmd: Command):
        """Handle /health command."""
        results = self.monitor.run_all_checks()

        msg = "🏥 **System Health**\n\n"
        for name, (ok, status) in results.items():
            emoji = "✅" if ok else "⚠️"
            msg += f"{emoji} **{name.title()}**: {status}\n"

        alerts = self.monitor.get_alerts()
        if alerts:
            msg += f"\n**Alerts ({len(alerts)})**:\n"
            for alert in alerts:
                msg += f"• {alert}\n"

        await self.gateway.send_followup(cmd.raw_interaction, msg)

    async def handle_tools(self, cmd: Command):
        """Handle /tools command."""
        tools = (
            self.orchestrator._tools.list_tools() if hasattr(self.orchestrator, "_tools") else []
        )

        if not tools:
            await self.gateway.send_followup(cmd.raw_interaction, "ℹ️ No tools registered")
            return

        msg = "🔧 **Available Tools**\n\n"
        for t in tools:
            desc = getattr(t, "description", "No description")[:50]
            msg += f"• `{t.name}`: {desc}\n"

        await self.gateway.send_followup(cmd.raw_interaction, msg)

    async def handle_screenshot(self, cmd: Command):
        """Handle /screenshot command."""
        url = cmd.args.get("url", "")
        full_page = cmd.args.get("full_page", False)

        if not url:
            await self.gateway.send_followup(cmd.raw_interaction, "❌ Please provide a URL")
            return

        await self.gateway.send_followup(
            cmd.raw_interaction, f"📸 Capturing screenshot of `{url}`..."
        )

        try:
            async with BrowserTool() as browser:
                result = await browser.screenshot(url, full_page=full_page)

                await self.gateway.send_followup(
                    cmd.raw_interaction,
                    content=f"📸 Screenshot: {result.title}",
                    file_path=str(result.path),
                    metadata={
                        "title": result.title,
                        "url": url,
                        "load_time_ms": result.load_time_ms,
                    },
                )
        except Exception as e:
            await self.gateway.send_followup(cmd.raw_interaction, f"❌ Screenshot failed: {e}")

    async def handle_docker(self, cmd: Command):
        """Handle /docker command."""
        import asyncio

        try:
            process = await asyncio.create_subprocess_exec(
                "docker",
                "ps",
                "--format",
                "table {{.Names}}\t{{.Status}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)

            if process.returncode == 0:
                output = stdout.decode().strip()
                status_msg = f"**🐳 Docker Status**\n```\n{output[:1900]}\n```"
            else:
                error = stderr.decode().strip()
                status_msg = f"**🐳 Docker Error**\n`docker ps` failed: {error}"
        except TimeoutError:
            status_msg = "❌ Docker status check timed out."
        except FileNotFoundError:
            status_msg = "❌ Docker CLI not found on host."
        except Exception as e:
            status_msg = f"❌ Error checking docker: {e}"

        await self.gateway.send_followup(cmd.raw_interaction, status_msg)

    async def handle_cron(self, cmd: Command):
        """Handle /cron command."""
        action = cmd.args.get("action", "list")
        from astra.tools.scheduler.tool import CronTool

        tool = CronTool()

        if action == "list":
            output = await tool.execute(action="list", project_path=".")
        elif action == "schedule":
            output = await tool.execute(
                action="schedule",
                cron=cmd.args.get("cron"),
                command=cmd.args.get("command"),
                description=cmd.args.get("description", ""),
                project_path=".",
            )
        elif action == "cancel":
            output = await tool.execute(action="cancel", job_id=cmd.args.get("job_id"))
        elif action == "run_now":
            output = await tool.execute(action="run_now", job_id=cmd.args.get("job_id"))
        elif action == "health":
            output = await tool.execute(action="health")
        else:
            output = f"❌ Unknown cron action: {action}"

        await self.gateway.send_followup(cmd.raw_interaction, output)

    async def handle_web(self, cmd: Command):
        """Handle /web search command."""
        query = cmd.args.get("query", "")
        if not query:
            await self.gateway.send_followup(
                cmd.raw_interaction, "❌ Please provide a search query"
            )
            return

        from astra.tools.search import SearchTool

        tool = SearchTool(max_results=3)
        try:
            result = await tool.execute(query=query)
            if len(result) > 1900:
                result = result[:1900] + "\n...(truncated)"
            await self.gateway.send_followup(
                cmd.raw_interaction, f"🔎 **Search Results for** `{query}`:\n\n{result}"
            )
        except Exception as e:
            await self.gateway.send_followup(cmd.raw_interaction, f"❌ Search failed: {e}")

    async def handle_cleanup(self, cmd: Command):
        """Handle /cleanup command."""
        max_age_days = cmd.args.get("max_age_days", 30)
        try:
            from astra.adapters.chromadb_store import ChromaDBStore

            store = ChromaDBStore()
            deleted = store.cleanup_stale_collections(max_age_days=max_age_days)

            if deleted:
                deleted_list = "\n".join([f"• `{name}`" for name in deleted])
                await self.gateway.send_followup(
                    cmd.raw_interaction,
                    f"🧹 Cleaned up {len(deleted)} stale collections:\n{deleted_list}",
                )
            else:
                await self.gateway.send_followup(
                    cmd.raw_interaction,
                    f"✅ No stale collections found (threshold: {max_age_days} days)",
                )
        except Exception as e:
            await self.gateway.send_followup(cmd.raw_interaction, f"❌ Cleanup failed: {e}")
