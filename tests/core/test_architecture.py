"""Tests for Architecture Generator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from astra.core.architecture import ArchitectureGenerator
from astra.interfaces.llm import LLMResponse


@pytest.mark.asyncio
async def test_generate_new(tmp_path):
    """Test generating doc when missing."""
    # Mock LLM
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(
        return_value=LLMResponse(
            content="# Test Arch Content",
            tool_calls=None,
            prompt_tokens=10,
            completion_tokens=10,
            total_tokens=20,
            model="test-ai",
        )
    )

    generator = ArchitectureGenerator(llm=mock_llm)
    # Mock dependencies
    generator._templates = MagicMock()
    generator._templates.get_template.return_value = "Mock Template"
    generator._file_ops = MagicMock()
    generator._file_ops.list_files.return_value = "src/"

    from unittest.mock import patch

    # Mock global function
    with patch(
        "astra.core.architecture.get_manifest_files_for_project",
        return_value={"package.json": "{}"},
    ):
        result = await generator.generate_if_missing(str(tmp_path))

    assert result is True
    assert (tmp_path / "ARCHITECTURE.md").exists()
    assert "# Test Arch Content" in (tmp_path / "ARCHITECTURE.md").read_text()


@pytest.mark.asyncio
async def test_skip_existing(tmp_path):
    """Test skipping if exists."""
    mock_llm = MagicMock()
    generator = ArchitectureGenerator(llm=mock_llm)

    (tmp_path / "ARCHITECTURE.md").write_text("# Existing")

    result = await generator.generate_if_missing(str(tmp_path))

    assert result is False
    assert (tmp_path / "ARCHITECTURE.md").read_text() == "# Existing"
