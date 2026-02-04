from unittest.mock import patch

from astra.config import get_config
from astra.core.monitor import Monitor
from astra.core.template_manager import TemplateManager


@patch("astra.core.monitor.shutil.disk_usage")
@patch("astra.core.monitor.psutil.virtual_memory")
def test_monitor_ascii_bars(mock_vm, mock_du):
    # Setup mocks for healthy system state
    mock_du.return_value.free = 100 * (1024**3)  # 100GB free
    mock_du.return_value.used = 50 * (1024**3)
    mock_du.return_value.total = 150 * (1024**3)

    mock_vm.return_value.percent = 40.0

    monitor = Monitor()
    # Clear cache to ensure mocks are used
    monitor.clear_cache()

    # Test Disk Check
    ok, msg = monitor.check_disk_usage()
    assert "[" in msg and "]" in msg
    assert "%" in msg

    # Test Memory Check
    ok, msg = monitor.check_memory()
    assert "[" in msg and "]" in msg
    assert "%" in msg


def test_template_manager_defaults(tmp_path):
    # Test with a temp dir
    tm = TemplateManager(template_dir=str(tmp_path))

    assert (tmp_path / "planning_feature.md").exists()
    assert (tmp_path / "architecture.md").exists()
    assert (tmp_path / "critic_review.md").exists()

    arch_content = tm.get_template("architecture")
    assert "Design Principles" in arch_content
    assert "Anti-Patterns" in arch_content

    critic_content = tm.get_template("critic_review")
    assert "Plan Critique" in critic_content


def test_config_critic_settings():
    config = get_config()
    # Check default
    assert config.orchestration.critic_loops == 5
    # Critic model might be None by default if not set in env
    assert hasattr(config.llm, "critic_model")
