"""Interactive setup wizard for ASTra."""

import json
import os
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()

def run_setup_wizard():
    """Run the interactive setup wizard."""
    console.print("[bold blue]🧙‍♂️ Welcome to the ASTra Setup Wizard![/bold blue]")
    console.print("This tool will help you configure your AI coding assistant.\n")

    # 1. Discord Token
    console.print("[bold]1. Discord Configuration[/bold]")
    discord_token = os.getenv("DISCORD_TOKEN")
    if discord_token:
        console.print("✅ DISCORD_TOKEN found in environment.")
        if Confirm.ask("Do you want to update it?", default=False):
            discord_token = Prompt.ask("Enter your Discord Bot Token", password=True)
    else:
        discord_token = Prompt.ask("Enter your Discord Bot Token", password=True)

    # 2. Admin User
    console.print("\n[bold]2. Security Configuration[/bold]")
    admin_user = Prompt.ask("Enter your Discord User ID (for admin access)")

    # 3. LLM Configuration
    console.print("\n[bold]3. AI Model Configuration[/bold]")
    llm_provider = Prompt.ask(
        "Select LLM Provider",
        choices=["ollama", "openai"],
        default="ollama"
    )

    model_name = ""
    if llm_provider == "ollama":
        model_name = Prompt.ask("Enter Ollama model name", default="qwen2.5-coder:7b")
    else:
        model_name = Prompt.ask("Enter OpenAI model name", default="gpt-4o")

    # 4. Save Configuration
    console.print("\n[bold green]💾 Saving Configuration...[/bold green]")

    # Save .env
    env_path = Path(".env")
    env_content = f"DISCORD_TOKEN={discord_token}\n"
    if llm_provider == "openai":
        api_key = Prompt.ask("Enter OpenAI API Key", password=True)
        env_content += f"OPENAI_API_KEY={api_key}\n"

    try:
        if env_path.exists():
            # Append or replace? For safety, let's just write/overwrite specific keys or append.
            # Simplified: Overwrite for wizard.
            if Confirm.ask(f"Overwrite existing {env_path}?", default=True):
                 env_path.write_text(env_content, encoding="utf-8")
        else:
            env_path.write_text(env_content, encoding="utf-8")
        console.print("✅ Saved .env")
    except Exception as e:
        console.print(f"[red]❌ Failed to save .env: {e}[/red]")

    # Save config.json
    config_path = Path("config.json")
    config_data = {
        "orchestration": {
            "security": {
                "admin_users": [admin_user]
            }
        },
        "llm": {
            "model": f"{llm_provider}/{model_name}" if llm_provider == "ollama" else model_name
        }
    }

    # Merge with existing if present to avoid losing other settings
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
            # Deep merge simple logic
            if "orchestration" not in existing: existing["orchestration"] = {}
            if "security" not in existing["orchestration"]: existing["orchestration"]["security"] = {}
            existing["orchestration"]["security"]["admin_users"] = [admin_user]

            if "llm" not in existing: existing["llm"] = {}
            existing["llm"]["model"] = config_data["llm"]["model"]

            config_data = existing
        except Exception:
            pass # Overwrite if corrupt

    try:
        config_path.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
        console.print("✅ Saved config.json")
    except Exception as e:
        console.print(f"[red]❌ Failed to save config.json: {e}[/red]")

    console.print("\n[bold blue]🎉 Setup Complete![/bold blue]")
    console.print("Run [bold]python astra/main.py run[/bold] to start your bot.")
