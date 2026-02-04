
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.handlers.system_handlers import SystemHandlers
from astra.interfaces.gateway import Command


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.llm.model = "gpt-4"
    config.orchestration.fallback_to_cloud = False
    config.model_dump.return_value = {
        "llm": {"model": "gpt-4", "context_limit": 8000},
        "orchestration": {"fallback_to_cloud": False}
    }

    # Mock deep getting/setting requires manual dict or real object.
    # Simple strategy: allow getattr to return MagicMocks that can be set.
    # But for "set" test we use real objects injected into config.

    return config

@pytest.fixture
def system_handlers(mock_config):
    gateway = MagicMock()
    gateway.send_followup = AsyncMock()
    orchestrator = MagicMock()

    # Patch Monitor globally or where it's imported from.
    # Since it is imported locally, we must patch the source.
    with patch("astra.core.monitor.Monitor"):
        handlers = SystemHandlers(gateway, orchestrator, mock_config)
        return handlers

@pytest.mark.asyncio
async def test_config_list_dms_user(system_handlers):
    """Test that /config list sends output via DM."""
    interaction = MagicMock()
    user_send = AsyncMock()
    interaction.user.send = user_send

    cmd = Command(
        name="config",
        args={"action": "list"},
        user_id="123",
        channel_id="channel-1",
        raw_interaction=interaction
    )

    await system_handlers.handle_config(cmd)

    # Verify DM sent
    # If this fails, it might be due to PropertyMock or something, but let's check.
    assert user_send.called, "DM send was not called on interaction.user.send"
    args = user_send.call_args[0][0]
    assert "**Full Configuration**" in args

    # Verify ephemeral confirmation - via gateway
    assert system_handlers.gateway.send_followup.called
    assert "Sent full configuration via DM" in system_handlers.gateway.send_followup.call_args[0][1]


@pytest.mark.asyncio
async def test_config_set_updates_value(system_handlers):
    """Test setting a config value."""
    interaction = MagicMock()

    cmd = Command(
        name="config",
        args={"action": "set", "key": "llm.model", "value": "claude-3"},
        user_id="123",
        channel_id="channel-1",
        raw_interaction=interaction
    )

    class LLM:
        pass
    llm = LLM()
    llm.model = "gpt-4"
    system_handlers.config.llm = llm

    await system_handlers.handle_config(cmd)

    assert system_handlers.config.llm.model == "claude-3"
    assert system_handlers.config.save.called

    # Check gateway call
    assert system_handlers.gateway.send_followup.called
    args = system_handlers.gateway.send_followup.call_args[0]
    # args: (interaction, content, ...)
    assert "Set `llm.model` to `claude-3`" in args[1]


@pytest.mark.asyncio
async def test_config_set_type_conversion(system_handlers):
    """Test boolean type conversion."""
    interaction = MagicMock()

    cmd = Command(
        name="config",
        args={"action": "set", "key": "orchestration.fallback_to_cloud", "value": "true"},
        user_id="123",
        channel_id="channel-1",
        raw_interaction=interaction
    )

    class Orch:
        fallback_to_cloud = False
    system_handlers.config.orchestration = Orch()

    await system_handlers.handle_config(cmd)

    assert system_handlers.config.orchestration.fallback_to_cloud is True
    assert system_handlers.gateway.send_followup.called
    assert "Set `orchestration.fallback_to_cloud` to `True`" in system_handlers.gateway.send_followup.call_args[0][1]


@pytest.mark.asyncio
async def test_config_get_value(system_handlers):
    """Test getting a value."""
    interaction = MagicMock()

    cmd = Command(
        name="config",
        args={"action": "get", "key": "llm.model"},
        user_id="123",
        channel_id="channel-1",
        raw_interaction=interaction
    )

    def get_conf(*keys):
        if keys == ("llm", "model"):
            return "gpt-4"
        return None

    system_handlers.config.get.side_effect = get_conf

    await system_handlers.handle_config(cmd)

    assert system_handlers.gateway.send_followup.called
    assert "gpt-4" in system_handlers.gateway.send_followup.call_args[0][1]
