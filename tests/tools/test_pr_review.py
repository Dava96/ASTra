"""Tests for PR review tool."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from astra.tools.pr_review import PRReviewTool


class TestPRReviewTool:
    """Test PR review functionality."""

    @pytest.fixture
    def mock_kg(self):
        """Create a mock Knowledge Graph."""
        kg = MagicMock()
        kg.get_dependents = MagicMock(return_value=[])
        return kg

    @pytest.fixture
    def mock_vcs(self):
        """Create a mock VCS."""
        vcs = AsyncMock()
        vcs.get_pr_files = AsyncMock(return_value=[])
        return vcs

    @pytest.fixture
    def pr_tool(self, mock_kg, mock_vcs):
        return PRReviewTool(knowledge_graph=mock_kg, vcs=mock_vcs)

    def test_tool_properties(self, pr_tool):
        """Test tool has correct properties."""
        assert pr_tool.name == "review_pr"
        assert "pr_number" in pr_tool.parameters["properties"]
        assert "repo" in pr_tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_review_with_no_files(self, pr_tool):
        """Test review when no files changed."""
        result = await pr_tool.execute(pr_number=1, repo="owner/repo")

        assert result["pr_number"] == 1
        assert result["repo"] == "owner/repo"
        assert "No changed files" in result["summary"]

    @pytest.mark.asyncio
    async def test_review_with_provided_files(self, pr_tool, mock_kg):
        """Test review with explicitly provided files."""
        mock_kg.get_dependents.return_value = ["file2.py", "file3.py"]

        result = await pr_tool.execute(
            pr_number=42,
            repo="test/repo",
            changed_files=["src/main.py"]
        )

        assert result["pr_number"] == 42
        assert result["impact_analysis"]["changed_files"] == 1
        mock_kg.get_dependents.assert_called_with("src/main.py")

    @pytest.mark.asyncio
    async def test_high_impact_detection(self, pr_tool, mock_kg):
        """Test detection of high-impact files."""
        # File with many dependents
        mock_kg.get_dependents.return_value = [
            f"dependent_{i}.py" for i in range(10)
        ]

        result = await pr_tool.execute(
            pr_number=1,
            repo="test/repo",
            changed_files=["core/utils.py"]
        )

        assert len(result["risks"]) > 0
        assert result["risks"][0]["severity"] == "high"

    @pytest.mark.asyncio
    async def test_dependency_change_recommendation(self, pr_tool):
        """Test recommendation when dependency files change."""
        result = await pr_tool.execute(
            pr_number=1,
            repo="test/repo",
            changed_files=["package.json", "src/app.js"]
        )

        assert any("Dependency changes" in r for r in result["recommendations"])

    @pytest.mark.asyncio
    async def test_review_without_kg(self):
        """Test review works without Knowledge Graph."""
        tool = PRReviewTool(knowledge_graph=None, vcs=None)

        result = await tool.execute(
            pr_number=1,
            repo="test/repo",
            changed_files=["file.py"]
        )

        assert result["summary"]
        assert result["impact_analysis"]["changed_files"] == 1
