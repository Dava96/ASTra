import asyncio
import logging
from pathlib import Path
from typing import Any

from astra.core.remote_provider import RemoteTemplateProvider
from astra.ingestion.parser import get_manifest_files_for_project
from astra.interfaces.gateway import Gateway, Message

logger = logging.getLogger(__name__)


class TemplateManager:
    """Manages prompt templates for different phases."""

    def __init__(self, template_dir: str | Path | None = None, gateway: Gateway | None = None):
        if template_dir:
            self._template_dir = Path(template_dir)
        else:
            self._template_dir = Path(__file__).parent.parent / "templates"
        self._cache: dict[str, str] = {}
        self._gateway = gateway
        self._remote = RemoteTemplateProvider()

        # Ensure directory exists
        self._create_defaults()

    def get_context_file_paths(
        self, project_path: str | Path, channel_id: str | None = None
    ) -> list[str]:
        """Detect project type and return relevant context file paths."""
        context_files = []
        project_path = Path(project_path)

        # 1. Global System Role (Always Included)
        system_path = self._template_dir / "system.md"
        if system_path.exists():
            context_files.append(str(system_path.resolve()))

        # 2. Detect Language & Framework via Manifests
        try:
            manifests = get_manifest_files_for_project(project_path)

            has_python = any(
                f in manifests for f in ["pyproject.toml", "requirements.txt", "setup.py"]
            )
            has_js_ts = any(f in manifests for f in ["package.json", "tsconfig.json"])
            has_rust = "Cargo.toml" in manifests

            # Helper to check/fetch
            def check_and_add(base_name: str, search_query: str):
                path = self._template_dir / base_name
                if path.exists():
                    context_files.append(str(path.resolve()))
                elif self._gateway and self._remote.is_enabled() and channel_id:
                    # Async fire-and-forget acquisition proposal
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(
                            self._propose_template_acquisition(base_name, search_query, channel_id)
                        )
                    except RuntimeError:
                        pass

            # python
            if has_python:
                check_and_add("python_conventions.md", "python best practices")

                for m_file in ["pyproject.toml", "requirements.txt", "setup.py"]:
                    if m_file in manifests and "fastapi" in manifests[m_file].lower():
                        check_and_add("fastapi_rules.md", "fastapi framework rules")
                        break

            # typescript/javascript
            if has_js_ts:
                is_ts = "tsconfig.json" in manifests
                if is_ts:
                    check_and_add("typescript_conventions.md", "typescript conventions")

                if "package.json" in manifests and "react" in manifests["package.json"].lower():
                    check_and_add("react_rules.md", "react best practices")

            if has_rust:
                check_and_add("rust_conventions.md", "rust language conventions")

        except Exception as e:
            logger.warning(f"Failed to detect context files: {e}")

        return context_files

    async def _propose_template_acquisition(
        self, filename: str, search_query: str, channel_id: str
    ):
        """Interactive flow to acquire a missing template."""
        if not self._gateway:
            return

        try:
            await self._gateway.send_message(
                Message(
                    content=str(f"ℹ️ Missing required template: `{filename}`. Searching SkillsMP..."),
                    channel_id=channel_id,
                )
            )

            results = self._remote.search(search_query, limit=3)
            if not results:
                await self._gateway.send_message(
                    Message(content="❌ No relevant skills found.", channel_id=channel_id)
                )
                return

            # Format results for user selection
            msg = f"Found {len(results)} potential templates for `{filename}`:\n"
            for i, res in enumerate(results):
                desc = res.get("description", "No description")[:100]
                msg += f"{i + 1}. **{res['name']}** - {desc}\n"

            msg += "\n*Reply with the number (1-3) to inspect and install, or 'cancel'.*"

            # Ask for selection (Simplified: simple prompt vs dropdown)
            # Real implementation needs 'request_input' or similar on Gateway.
            # Assuming request_confirmation style logic or waiting for next message.
            # Since request_confirmation returns Bool, we can't get text easily without new Gateway method.
            # Fallback: Just offer the first one for YES/NO for MVP Refactor.

            top_result = results[0]
            should_inspect = await self._gateway.request_confirmation(
                channel_id,
                f"Found skill: **{top_result['name']}**\n{top_result.get('description')}\n\nInspect and install?",
            )

            if not should_inspect:
                return

            # Fetch and Show (Sandbox)
            content = self._remote.fetch_content(top_result["id"])
            if not content:
                await self._gateway.send_message(
                    Message(content="❌ Failed to fetch content.", channel_id=channel_id)
                )
                return

            # Show preview
            preview = f"## Preview: {filename}\n```markdown\n{content[:500]}...\n```\n(Truncated)"
            await self._gateway.send_message(
                Message(content=preview, channel_id=channel_id)
            )

            is_safe = await self._gateway.request_confirmation(
                channel_id, "⚠️ **Security Check**: Do you approve this content for installation?"
            )

            if is_safe:
                self.update_template(filename.replace(".md", ""), content)
                await self._gateway.send_message(
                    Message(
                        content=f"✅ Installed `{filename}`. Rerun the task to apply.",
                        channel_id=channel_id,
                    )
                )

        except Exception as e:
            logger.error(f"Acquisition flow failed: {e}")

    def get_template(self, name: str) -> str:
        """Get a template by name (cached)."""
        if name in self._cache:
            return self._cache[name]

        # Try mapping common names to filenames
        filename = name if name.endswith(".md") else f"{name}.md"
        path = self._template_dir / filename

        if path.exists():
            content = path.read_text(encoding="utf-8")
            self._cache[name] = content
            return content

        raise FileNotFoundError(f"Template '{name}' not found at {path}")

    def render(self, name: str, **kwargs: Any) -> str:
        """Load and render a template with variables."""
        template = self.get_template(name)

        # Simple string replacement for now (lighter than jinja2)
        # We can upgrade to jinja2 if complexity grows
        content = template
        for key, value in kwargs.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in content:
                content = content.replace(placeholder, str(value))

        return content

    def update_template(self, name: str, content: str) -> None:
        """Update a template file."""
        filename = name if name.endswith(".md") else f"{name}.md"
        path = self._template_dir / filename
        path.write_text(content, encoding="utf-8")
        self._cache[name] = content
        logger.info(f"Updated template: {name}")

    def list_templates(self) -> list[str]:
        """List available templates."""
        return [f.name for f in self._template_dir.glob("*.md")]

    def reset_cache(self) -> None:
        """Clear the memory cache."""
        self._cache.clear()

    def _create_defaults(self) -> None:
        """Create default templates if missing."""
        self._template_dir.mkdir(parents=True, exist_ok=True)

        # Planning Template
        plan_path = self._template_dir / "planning_feature.md"
        if not plan_path.exists():
            plan_path.write_text(
                "# Implementation Plan for: {{request}}\n\n"
                "## Goal\n"
                "Describe the high-level goal.\n\n"
                "## Proposed Changes\n"
                "List specific files and changes.\n"
                "- [ ] `path/to/file.py`: Description of change\n\n"
                "## Verification\n"
                "How will we verify this works?"
            )

        # Architecture Template
        arch_path = self._template_dir / "architecture.md"
        if not arch_path.exists():
            arch_path.write_text(
                "# Architecture: {{project_name}}\n\n"
                "## Overview\n"
                "{{overview}}\n\n"
                "## Design Principles\n"
                "- Principle 1\n"
                "- Principle 2\n\n"
                "## Anti-Patterns to Avoid\n"
                "- Anti-pattern 1\n"
                "- Anti-pattern 2\n\n"
                "## Components\n"
                "{{components}}\n\n"
                "## Data Flow\n"
                "{{data_flow}}"
            )

        # Critic Review Template
        critic_path = self._template_dir / "critic_review.md"
        if not critic_path.exists():
            critic_path.write_text(
                "# Plan Critique\n\n"
                "## Analysis\n"
                "**Why:** Does this solve the user's problem? Is the 'Why' clear?\n"
                "**What:** Are the proposed changes sufficient? Anything missing?\n"
                "**How:** Is the implementation approach sound? Any efficient alternatives?\n\n"
                "## Benefits & Downsides\n"
                "- **Benefits**: ...\n"
                "- **Downsides**: ...\n\n"
                "## Questions\n"
                "1. ...\n"
                "2. ...\n\n"
                "## Verdict\n"
                "APPROVE / REQUEST_CHANGES\n"
                "(If REQUEST_CHANGES, provide specific feedback below)"
            )

        # Pull Request Template
        pr_path = self._template_dir / "pr_description.md"
        if not pr_path.exists():
            pr_path.write_text("## Summary\n{{summary}}\n\n## Changes\n{{changes}}")
