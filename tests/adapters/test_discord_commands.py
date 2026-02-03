from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astra.adapters.gateways.discord.commands import register_all_commands


@pytest.fixture
def mock_gateway():
    gateway = MagicMock()
    gateway.is_user_authorized.return_value = True
    gateway.is_admin.return_value = True
    gateway._config.llm.planning_model = "plan-model"
    gateway._config.llm.coding_model = "code-model"
    # Mock auth manager for auth list
    gateway._auth.get_authorized_users.return_value = ["123"]
    return gateway

@pytest.fixture
def mock_interaction():
    interaction = MagicMock()
    interaction.user.id = "123"
    interaction.channel_id = "456"
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction

@pytest.mark.asyncio
async def test_register_and_execute_commands(mock_gateway, mock_interaction):
    # Registry to capture the inner functions
    registry = {}

    def command_decorator(name, description=""):
        def decorator(func):
            registry[name] = func
            return func
        return decorator

    # Mock Tree
    mock_tree = MagicMock()
    mock_tree.command.side_effect = command_decorator

    # Capture groups
    groups = {}
    def add_command(cmd):
        if hasattr(cmd, "name"):
            groups[cmd.name] = cmd
    mock_tree.add_command.side_effect = add_command

    # Callback Mocks
    on_feature = AsyncMock()
    on_fix = AsyncMock()
    on_quick = AsyncMock()
    on_checkout = AsyncMock()
    on_status = AsyncMock()
    on_cancel = AsyncMock()
    on_last = AsyncMock()
    on_approve = AsyncMock()
    on_revise = AsyncMock()
    on_screenshot = AsyncMock()

    # Register
    register_all_commands(
        mock_gateway, mock_tree, handlers={},
        on_feature=on_feature, on_fix=on_fix, on_quick=on_quick,
        on_checkout=on_checkout, on_status=on_status, on_cancel=on_cancel,
        on_last=on_last, on_approve=on_approve, on_revise=on_revise,
        on_screenshot=on_screenshot
    )

    # --- Test Core Commands ---

    # Feature
    assert "feature" in registry
    await registry["feature"](mock_interaction, request="Add login")
    on_feature.assert_called_once()
    assert on_feature.call_args[0][0].args["request"] == "Add login"

    # Fix
    await registry["fix"](mock_interaction, description="Fix bug")
    on_fix.assert_called_once()

    # Quick
    await registry["quick"](mock_interaction, file="main.py", change="fix typo")
    on_quick.assert_called_once()

    # Checkout
    await registry["checkout"](mock_interaction, repo="user/repo")
    on_checkout.assert_called_once()

    # Status
    await registry["status"](mock_interaction)
    on_status.assert_called_once()

    # Cancel
    await registry["cancel"](mock_interaction)
    on_cancel.assert_called_once()

    # Last
    await registry["last"](mock_interaction)
    on_last.assert_called_once()

    # Approve
    await registry["approve"](mock_interaction, task_id="1")
    on_approve.assert_called_once()

    # Revise
    await registry["revise"](mock_interaction, task_id="1", feedback="bad")
    on_revise.assert_called_once()

    # Screenshot
    await registry["screenshot"](mock_interaction, url="http://google.com")
    on_screenshot.assert_called_once()

    # Help
    await registry["help"](mock_interaction)
    mock_interaction.response.send_message.assert_called()

    # --- Test Groups ---

    # Auth Group
    auth_group = groups.get("auth")
    assert auth_group is not None
    # Cannot easily invoke app_commands.Group.command directly as simple funcs
    # But checking register_all_commands source, group commands are defined as decorators
    # inside register_all_commands but attached to the group instance.
    # Actually, app_commands.Group.command is a decorator just like tree.command.
    # We need to spy on auth_group.command too? No, the group is created inside the function.
    # The group commands are defined using @auth_group.command.
    # Since auth_group is a real object (app_commands.Group), its .command method is real.
    # We might need to mock app_commands.Group to capture those too.

@pytest.mark.asyncio
async def test_auth_commands(mock_gateway, mock_interaction):
    # We need to patch app_commands.Group to intercept its commands
    with patch("discord.app_commands.Group") as MockGroup:
        group_registry = {}

        # When a group is instantiated, we want to capture its .command decorator
        mock_group_instance = MockGroup.return_value

        def group_command_decorator(name, description=""):
            def decorator(func):
                group_registry[name] = func
                group_registry[func.__name__] = func # Store by function name too
                return func
            return decorator

        mock_group_instance.command.side_effect = group_command_decorator

        # Call register
        register_all_commands(
            mock_gateway, MagicMock(), handlers={},
            on_feature=AsyncMock(), on_fix=AsyncMock(), on_quick=AsyncMock(),
            on_checkout=AsyncMock(), on_status=AsyncMock(), on_cancel=AsyncMock(),
            on_last=AsyncMock(), on_model=AsyncMock(), on_cron=AsyncMock(),
            on_web=AsyncMock(), on_auth=AsyncMock(), on_cleanup=AsyncMock(),
            on_config=AsyncMock(), on_tools=AsyncMock(), on_health=AsyncMock()
        )

        # Test Auth Add
        user = MagicMock()
        user.mention = "@user"
        user.id = "999"

        # Add (Success)
        mock_gateway.add_authorized_user.return_value = True
        await group_registry["add"](mock_interaction, user=user)
        mock_interaction.response.send_message.assert_called_with("✅ Added @user to authorized users.")

        mock_interaction.reset_mock()

        # Add (Fail)
        mock_gateway.add_authorized_user.return_value = False
        await group_registry["add"](mock_interaction, user=user)

        assert mock_interaction.response.send_message.called
        # Check call args (could be positional or keyword)
        call_args = mock_interaction.response.send_message.call_args
        args = call_args[0]
        kwargs = call_args[1]

        # Combine args and kwargs values to search for message
        all_text = " ".join([str(a) for a in args] + [str(v) for v in kwargs.values()])
        assert "already authorized" in all_text

        # Remove
        mock_gateway.remove_authorized_user.return_value = True
        await group_registry["remove"](mock_interaction, user=user)
        mock_interaction.response.send_message.assert_called_with("✅ Removed @user from authorized users.")

        mock_interaction.reset_mock()

        # List
        mock_interaction.reset_mock()
        mock_gateway.is_admin.return_value = True
        mock_gateway._auth.get_authorized_users.return_value = ["123"]

        await group_registry["auth_list"](mock_interaction)

        assert mock_interaction.response.send_message.called
        args, kwargs = mock_interaction.response.send_message.call_args
        assert len(args) > 0, f"Call args empty: {args}, kwargs: {kwargs}"
        assert "Authorized Users" in args[0]

@pytest.mark.asyncio
async def test_config_model_commands(mock_gateway, mock_interaction):
    with patch("discord.app_commands.Group") as MockGroup:
        group_registry = {}
        mock_group_instance = MockGroup.return_value

        def group_command_decorator(name, description=""):
            def decorator(func):
                group_registry[name] = func
                return func
            return decorator
        mock_group_instance.command.side_effect = group_command_decorator

        register_all_commands(
            mock_gateway, MagicMock(), handlers={},
            on_feature=AsyncMock(), on_fix=AsyncMock(), on_quick=AsyncMock(),
            on_checkout=AsyncMock(), on_status=AsyncMock(), on_cancel=AsyncMock(),
            on_last=AsyncMock(), on_model=AsyncMock(), on_cron=AsyncMock(),
            on_web=AsyncMock(), on_auth=AsyncMock(), on_cleanup=AsyncMock(),
            on_config=AsyncMock(), on_tools=AsyncMock(), on_health=AsyncMock()
        )

        # We have multiple groups (auth, config, model). They all use the same mock instance?
        # Yes, standard Mock behavior returns same child.
        # But names might collide if multiple groups have same command name (e.g. 'list').
        # register_all_commands creates: auth_group, config_group, model_group.
        # It calls app_commands.Group(name="auth"), then Group(name="config").
        # If we return the SAME instance, 'list' will be overwritten.
        # We need side_effect for Group constructor?
        pass

# Refined test for multiple groups
@pytest.mark.asyncio
async def test_commands_groups_isolation(mock_gateway, mock_interaction):
    # Strategy: capture based on the group name passed to constructor

    group_cmds = {"auth": {}, "config": {}, "model": {}, "cron": {}, "mfa": {}}

    # Store mocked groups
    mock_groups = []

    def MockGroupSideEffect(name=None, description=None):
        m = MagicMock()
        mock_groups.append(m)
        current_group_name = name

        def cmd_dec(name, description=""):
            def d(func):
                group_cmds[current_group_name][name] = func
                return func
            return d

        m.command.side_effect = cmd_dec
        return m

    with patch("discord.app_commands.Group", side_effect=MockGroupSideEffect):
        register_all_commands(
            mock_gateway, MagicMock(), handlers={},
            on_feature=AsyncMock(), on_fix=AsyncMock(), on_quick=AsyncMock(),
            on_checkout=AsyncMock(), on_status=AsyncMock(), on_cancel=AsyncMock(),
            on_last=AsyncMock(), on_model=AsyncMock(), on_cron=AsyncMock(),
            on_web=AsyncMock(), on_auth=AsyncMock(), on_cleanup=AsyncMock(),
            on_config=AsyncMock(), on_tools=AsyncMock(), on_health=AsyncMock()
        )

        # Config List
        await group_cmds["config"]["list"](mock_interaction)
        mock_interaction.response.send_message.assert_called()

        # Config Get
        mock_gateway._config.some_val = "123"
        await group_cmds["config"]["get"](mock_interaction, key="some_val")
        assert "123" in mock_interaction.response.send_message.call_args[0][0]

        # Model Current
        await group_cmds["model"]["current"](mock_interaction)
        assert "Current Models" in mock_interaction.response.send_message.call_args[0][0]

        # Model Set (requires mocking file ops)
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value='{"llm":{}}'), \
             patch("pathlib.Path.write_text") as mock_write:

             await group_cmds["model"]["set"](mock_interaction, model="gpt-5", target="planning")
             assert "gpt-5" in mock_write.call_args[0][0]

@pytest.mark.asyncio
async def test_authorization_checks(mock_gateway, mock_interaction):
    # Registry to capture the inner functions
    registry = {}
    def command_decorator(name, description=""):
        def decorator(func):
            registry[name] = func
            return func
        return decorator

    mock_tree = MagicMock()
    mock_tree.command.side_effect = command_decorator

    register_all_commands(
            mock_gateway, mock_tree, handlers={},
            on_feature=AsyncMock(), on_fix=AsyncMock(), on_quick=AsyncMock(),
            on_checkout=AsyncMock(), on_status=AsyncMock(), on_cancel=AsyncMock(),
            on_last=AsyncMock()
    )

    # Set Unauthorized
    mock_gateway.is_user_authorized.return_value = False

    # Try feature
    await registry["feature"](mock_interaction, request="foo")
    mock_interaction.response.send_message.assert_called_with("⛔ Not authorized.", ephemeral=True)
