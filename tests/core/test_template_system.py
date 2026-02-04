from unittest.mock import patch

import pytest

from astra.core.template_manager import TemplateManager
from astra.tools.aider_tool import AiderTool

# Mock data
MOCK_PYPROJECT = """
[project]
name = "test-project"
dependencies = ["fastapi", "uvicorn"]
"""

MOCK_PACKAGE_JSON_REACT = """
{
  "name": "test-react",
  "dependencies": {
    "react": "^18.2.0"
  }
}
"""


@pytest.fixture
def template_manager(tmp_path):
    # Setup mock templates
    tm = TemplateManager(template_dir=tmp_path / "templates")
    (tmp_path / "templates").mkdir(exist_ok=True)
    (tmp_path / "templates" / "system.md").write_text("system")
    (tmp_path / "templates" / "python_conventions.md").write_text("python")
    (tmp_path / "templates" / "fastapi_rules.md").write_text("fastapi")
    (tmp_path / "templates" / "typescript_conventions.md").write_text("ts")
    (tmp_path / "templates" / "react_rules.md").write_text("react")
    return tm


@patch("astra.core.template_manager.get_manifest_files_for_project")
def test_detect_python_fastapi(mock_manifests, template_manager, tmp_path):
    mock_manifests.return_value = {"pyproject.toml": MOCK_PYPROJECT}

    paths = template_manager.get_context_file_paths(tmp_path)

    assert any("system.md" in p for p in paths)
    assert any("python_conventions.md" in p for p in paths)
    assert any("fastapi_rules.md" in p for p in paths)
    assert not any("typescript_conventions.md" in p for p in paths)


@patch("astra.core.template_manager.get_manifest_files_for_project")
def test_detect_react_ts(mock_manifests, template_manager, tmp_path):
    mock_manifests.return_value = {"package.json": MOCK_PACKAGE_JSON_REACT, "tsconfig.json": "{}"}

    paths = template_manager.get_context_file_paths(tmp_path)

    assert any("system.md" in p for p in paths)
    assert any("typescript_conventions.md" in p for p in paths)
    assert any("react_rules.md" in p for p in paths)
    assert not any("python_conventions.md" in p for p in paths)


def test_aider_tool_build_command():
    tool = AiderTool()
    cmd = tool._build_command(
        message="fix it", files=["main.py"], context_files=["/tmp/system.md", "/tmp/python.md"]
    )

    # Verify structure
    assert "--model" in cmd
    assert "--message" in cmd
    assert "main.py" in cmd

    # Verify context injection
    assert "--read" in cmd
    read_indices = [i for i, x in enumerate(cmd) if x == "--read"]
    assert len(read_indices) == 2
    assert cmd[read_indices[0] + 1] == "/tmp/system.md"
    assert cmd[read_indices[1] + 1] == "/tmp/python.md"


def test_aider_tool_build_command_no_context():
    tool = AiderTool()
    cmd = tool._build_command(message="fix it", files=["main.py"], context_files=None)

    assert "--read" not in cmd
    assert "--model" in cmd
