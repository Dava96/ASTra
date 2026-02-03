
from astra.config import get_config
from astra.core.monitor import Monitor
from astra.core.template_manager import TemplateManager


def test_monitor_ascii_bars():
    monitor = Monitor()

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
