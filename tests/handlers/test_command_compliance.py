"""Tests to ensure all Discord commands are correctly registered and handled."""

import ast
import inspect

from astra.adapters.gateways.discord import DiscordGateway
from astra.handlers.command_handlers import CommandHandler


def test_command_handler_mapping():
    """Verify all built-in commands in DiscordGateway have handlers in CommandHandler."""
    # 1. Get command handler methods
    handler_methods = [
        name for name, _ in inspect.getmembers(CommandHandler, predicate=inspect.isfunction)
    ]

    # 2. Extract expected handler pattern from DiscordGateway.register_built_in_commands parameters
    sig = inspect.signature(DiscordGateway.register_built_in_commands)
    params = sig.parameters

    # Built-in commands are passed as on_xxx arguments
    command_args = [p for p in params if p.startswith("on_")]

    assert len(command_args) > 5, "Too few command arguments found in register_built_in_commands"

    # Check if each command has a corresponding handle_xxx method in CommandHandler
    for arg in command_args:
        cmd_name = arg[3:]  # remove "on_"
        expected_handler = f"handle_{cmd_name}"
        assert expected_handler in handler_methods, (
            f"CommandHandler missing {expected_handler} for {arg}"
        )


def test_main_registration_completeness():
    """Verify main.py registers all available command handlers."""

    # Read astra/main.py to check registration calls
    with open("astra/main.py", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    # Look for gateway.register_built_in_commands call
    registration_found = False
    registered_handlers = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (
            isinstance(node.func, ast.Attribute) and node.func.attr == "register_built_in_commands"
        ):
            registration_found = True
            for keyword in node.keywords:
                registered_handlers.add(keyword.arg)

    assert registration_found, "Could not find gateway.register_built_in_commands call in main.py"

    # Get all expected (on_xxx) args from DiscordGateway
    sig = inspect.signature(DiscordGateway.register_built_in_commands)
    expected_handlers = [p for p in sig.parameters if p.startswith("on_")]

    for expected in expected_handlers:
        # Some might be optional (None default), but they should generally be registered in main.py
        # Check if it's registered
        assert expected in registered_handlers, f"Command {expected} is not registered in main.py"


def test_gateway_slash_commands_match_registration():
    """Verify all slash commands defined in CORE commands are covered by registration args."""
    # Commands are now in astra/core/commands.py
    with open("astra/core/commands.py", encoding="utf-8") as f:
        content = f.read()
        tree = ast.parse(content)

    command_names = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "register_command"
            and node.keywords
        ):
            # Look for name arg
            for kw in node.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    command_names.add(kw.value.value)

    # Some commands are groups or special, but basic ones should match on_xxx args
    sig = inspect.signature(DiscordGateway.register_built_in_commands)
    on_args = {p[3:] for p in sig.parameters if p.startswith("on_")}

    # Basic commands like feature, fix, quick, status, etc.
    essential_commands = {"feature", "fix", "quick", "status", "cancel", "last", "checkout"}
    for cmd in essential_commands:
        assert cmd in command_names, f"Essential slash command /{cmd} not found in core/commands.py"
        assert cmd in on_args, f"Essential command {cmd} missing from registration interface"
