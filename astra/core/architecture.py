"""Architecture documentation generator."""

import logging
from pathlib import Path

from astra.adapters.llm_client import LiteLLMClient
from astra.core.template_manager import TemplateManager
from astra.ingestion.parser import get_manifest_files_for_project
from astra.interfaces.llm import ChatMessage
from astra.tools.file_ops import FileOps

logger = logging.getLogger(__name__)

class ArchitectureGenerator:
    """Generates architecture documentation for a project."""

    def __init__(self, llm: LiteLLMClient | None = None):
        self._llm = llm or LiteLLMClient()
        self._templates = TemplateManager()
        self._file_ops = FileOps()

    async def generate_if_missing(self, project_path: str) -> bool:
        """Generate ARCHITECTURE.md if it doesn't exist."""
        path = Path(project_path) / "ARCHITECTURE.md"
        if path.exists():
            return False

        logger.info(f"Generating ARCHITECTURE.md for {project_path}")
        try:
            doc_content = await self._analyze_and_generate(project_path)
            path.write_text(doc_content, encoding="utf-8")
            logger.info("ARCHITECTURE.md generated successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to generate architecture doc: {e}")
            return False

    async def _analyze_and_generate(self, project_path: str) -> str:
        """Analyze project structure and generate documentation content."""

        # 1. Gather Context
        manifests = get_manifest_files_for_project(project_path)
        manifest_text = "\n".join([f"## {k}\n{v}" for k, v in manifests.items()])

        tree = self._file_ops.list_files(project_path, max_depth=2)

        # 2. Prompt LLM
        prompt = (
            f"Analyze the following project structure and dependencies to document its architecture.\n\n"
            f"### Directory Structure\n{tree}\n\n"
            f"### Dependencies\n{manifest_text}\n\n"
            f"Please fill out the following template. Be concise but specific about patterns inferred from the definitions available.\n"
            f"Determine the 'Type' (e.g. Django Monolith, React SPA, libraries, etc.) and 'Rules' that likely apply.\n"
            f"Be sure to populate the 'Anti-Patterns' and 'Design Principles' sections.\n\n"
            f"Template to fill:\n"
            f"{self._templates.get_template('architecture')}\n\n"
            f"Return ONLY the filled markdown document."
        )

        messages = [
             ChatMessage(role="system", content="You are a senior software architect. Document the architecture of the provided codebase."),
             ChatMessage(role="user", content=prompt)
        ]

        # 3. Get Response
        response = await self._llm.chat(messages)
        return response.content

