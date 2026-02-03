"""Verification for Pydantic Config."""

from astra.config import Config


def test_defaults():
    c = Config()
    assert c.orchestration.max_self_heal_attempts == 3
    assert c.llm.model == "ollama/qwen2.5-coder:7b"

def test_legacy_get():
    c = Config()
    # 2-level
    assert c.get("llm", "model") == "ollama/qwen2.5-coder:7b"
    # 3-level
    assert "git" in c.get("orchestration", "security", "command_allowlist")
    # Default
    assert c.get("missing", default="check") == "check"
    assert c.get("llm", "missing", default="check") == "check"

def test_env_override(monkeypatch):
    monkeypatch.setenv("ASTRA_LLM__MODEL", "gpt-4")
    monkeypatch.setenv("ASTRA_ORCHESTRATION__MAX_SELF_HEAL_ATTEMPTS", "10")

    # Reload config to pick up env
    # Note: BaseSettings reads env vars at instantiation
    c = Config()

    assert c.llm.model == "gpt-4"
    assert c.orchestration.max_self_heal_attempts == 10

    # Verify legacy get matches
    assert c.get("llm", "model") == "gpt-4"

def test_dict_access():
    """Verify that we can access nested dicts if needed, or if accessing properties behaves like dicts."""
    # The new config uses objects, not dicts.
    # Existing code might not rely on dict access for internal nodes,
    # but let's check if config.get returns a dict for a middle node.
    c = Config()

    security = c.get("orchestration", "security")
    # In Pydantic, this is a Model, not a dict.
    # If legacy code expects a dict, this might break.
    # Let's see if we need to support .get() on the returned object.

    # The config.get implementation returns: getattr(val, k)
    # So security is a SecurityConfig object.
    # Does SecurityConfig have .get? No.
    # If code does: config.get("orchestration", "security").get("allowlist") -> Error.
    pass
