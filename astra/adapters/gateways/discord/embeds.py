"""Discord embed builders for rich message formatting."""

import discord


def build_help_embed() -> discord.Embed:
    """Build the help command embed."""
    embed = discord.Embed(
        title="🤖 ASTra Commands",
        description="Autonomous AI coding assistant",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="📦 Task Commands",
        value=(
            "**/feature** `<request>` - Request a new feature\n"
            "**/fix** `<description>` - Fix a bug or issue\n"
            "**/quick** `<file>` `<change>` - Quick single-file edit\n"
            "**/web** `<query>` - Search the web"
        ),
        inline=False,
    )
    embed.add_field(
        name="📂 Project Commands",
        value=(
            "**/checkout** `<repo>` - Set active repository\n"
            "**/status** - Check queue and task status\n"
            "**/cancel** - Cancel current task\n"
            "**/last** - Show last task result\n"
            "**/history** - View recent tasks\n"
            "**/docker** - Check Docker status"
        ),
        inline=False,
    )
    embed.add_field(
        name="⚙️ Configuration & Tools",
        value=(
            "**/config list** - Show all config options\n"
            "**/config get** `<key>` - Get a config value\n"
            "**/model set** `<model>` - Switch LLM model\n"
            "**/cron list/schedule** - Manage cron jobs\n"
            "**/auth add/remove/list** - Manage users (admin)"
        ),
        inline=False,
    )
    embed.set_footer(text="Use /config list to see all configuration options")
    return embed


def build_config_embed(config) -> discord.Embed:
    """Build the configuration overview embed."""
    embed = discord.Embed(title="⚙️ Configuration Options", color=discord.Color.green())

    # LLM settings
    planning = config.llm.planning_model or "not set"
    coding = config.llm.coding_model or "same as planning"
    embed.add_field(
        name="🧠 LLM", value=f"**Planning:** `{planning}`\n**Coding:** `{coding}`", inline=False
    )

    # Git settings
    git = config.git
    embed.add_field(
        name="📁 Git",
        value=(
            f"**Auto PR:** `{git.auto_pr}`\n"
            f"**Branch Prefix:** `{git.branch_prefix}`\n"
            f"**Review Required:** `{git.review_required}`"
        ),
        inline=False,
    )

    # Security settings
    sec = config.orchestration.security
    embed.add_field(
        name="🔒 Security",
        value=(
            f"**Auto Install Packages:** `{sec.auto_install_packages}`\n"
            f"**Shell Permission Required:** `{sec.require_permission_for_shell}`"
        ),
        inline=False,
    )

    return embed


def build_status_embed(status: dict) -> discord.Embed:
    """Build task status embed."""
    embed = discord.Embed(title="📊 Task Status", color=discord.Color.blue())

    if status.get("current_task"):
        task = status["current_task"]
        embed.add_field(
            name="🔄 Current Task",
            value=f"**{task.get('name', 'Unknown')}**\n{task.get('status', 'Working...')}",
            inline=False,
        )
    else:
        embed.add_field(name="Status", value="✅ No active tasks", inline=False)

    if status.get("queue_length", 0) > 0:
        embed.add_field(
            name="📋 Queue", value=f"{status['queue_length']} tasks waiting", inline=True
        )

    return embed
