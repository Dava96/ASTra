"""Interactive setup wizard for ASTra."""

import os
import re
import shutil
from pathlib import Path

import requests
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from astra.config import get_config

console = Console()


def _save_env_file(secrets: dict[str, str]) -> None:
    """Save secrets to .env file, preserving existing keys not in secrets."""
    env_path = Path(".env")
    current_lines = []
    if env_path.exists():
        current_lines = env_path.read_text(encoding="utf-8").splitlines()

    new_lines = []
    processed_keys = set()

    # Update existing keys
    for line in current_lines:
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            if key in secrets:
                new_lines.append(f"{key}={secrets[key]}")
                processed_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Add new keys
    for key, val in secrets.items():
        if key not in processed_keys:
            new_lines.append(f"{key}={val}")

    # Ensure newline at end
    if new_lines and new_lines[-1] != "":
        new_lines.append("")

    try:
        env_path.write_text("\n".join(new_lines), encoding="utf-8")
        console.print("[green]✅ Saved secrets to .env[/green]")
    except Exception as e:
        console.print(f"[red]❌ Failed to save .env: {e}[/red]")


def _get_ollama_models(host: str = "http://localhost:11434") -> list[str]:
    """Fetch available Ollama models dynamically."""
    try:
        response = requests.get(f"{host}/api/tags", timeout=1)
        if response.status_code == 200:
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            return sorted(models)
    except Exception:
        pass
    return []


def _validate_discord_token(token: str) -> bool:
    """Basic structural validation for Discord tokens."""
    # Tokens usually have 3 parts separated by dots
    return bool(re.match(r"[\w-]{24}\.[\w-]{6}\.[\w-]{27,}", token))


def run_setup_wizard():
    """Run the interactive setup wizard."""
    console.print(
        Panel.fit(
            "[bold blue]🧙‍♂️ Welcome to the ASTra Setup Wizard![/bold blue]\n"
            "Configure your AI Agent's core settings, security, and tools."
        )
    )

    config = get_config()
    secrets: dict[str, str] = {}

    # --- 1. Core Connectivity (Discord) ---
    console.print("\n[bold]1. Connectivity (Discord)[/bold]")
    discord_token = os.getenv("DISCORD_TOKEN")

    if discord_token:
        console.print(f"Current Token: [green]{discord_token[:4]}...{discord_token[-4:]}[/green]")
        if Confirm.ask("Update Discord Token?", default=False):
            discord_token = None # Force re-entry

    if not discord_token:
        while True:
            token = Prompt.ask("Enter Discord Bot Token (input hidden)", password=True)

            if not token:
                console.print("[yellow]⚠️ No input received. Try pasting by right-clicking or Ctrl+Shift+V.[/yellow]")
                continue

            if _validate_discord_token(token) or Confirm.ask("Token format looks unusual. Use anyway?", default=False):
                secrets["DISCORD_TOKEN"] = token
                break


    # --- 2. Security (Admin) ---
    console.print("\n[bold]2. Security & permissions[/bold]")

    current_admins = config.orchestration.security.admin_users
    console.print(f"Current Admins: {current_admins}")

    if not current_admins or Confirm.ask("Update Admin User IDs?", default=False):
        admin_input = Prompt.ask("Enter Admin Discord User IDs (comma separated)")
        # Clean and split
        admin_ids = [uid.strip() for uid in admin_input.split(",") if uid.strip()]
        config.orchestration.security.admin_users = admin_ids


    # --- 3. AI Model Configuration ---
    console.print("\n[bold]3. AI Model Configuration[/bold]")

    current_llm_provider = "ollama" if "ollama" in config.llm.model else "openai"
    llm_provider = Prompt.ask(
        "Select LLM Provider",
        choices=["ollama", "openai"],
        default=current_llm_provider
    )

    if llm_provider == "ollama":
        config.llm.host = Prompt.ask("Enter Ollama Host", default=config.llm.host)

        # O(1) Optimization: Auto-fetch models
        available_models = _get_ollama_models(config.llm.host)
        model_default = config.llm.model if "ollama" in config.llm.model else "ollama_chat/qwen2.5-coder:7b"

        if available_models:
            choices = available_models + ["Other (Manual Entry)"]
            selected_model = Prompt.ask(
                "Select installed model",
                choices=choices,
                default=choices[0]
            )
            if selected_model == "Other (Manual Entry)":
                 config.llm.model = Prompt.ask("Enter Ollama model", default=model_default)
            else:
                 # Prefix correctly for litellm
                 prefix = "ollama_chat/" if not selected_model.startswith("ollama") else ""
                 config.llm.model = f"{prefix}{selected_model}"
        else:
            config.llm.model = Prompt.ask("Enter Ollama model", default=model_default)

    else:
        config.llm.model = Prompt.ask(
            "Enter OpenAI model",
            default=config.llm.model if "gpt" in config.llm.model else "gpt-4o"
        )
        secrets["OPENAI_API_KEY"] = Prompt.ask("Enter OpenAI API Key", password=True)


    # --- 4. Features & Integrations (Smart Detection) ---
    console.print("\n[bold]4. Features & Integrations[/bold]")

    # SkillsMP
    if Confirm.ask(f"Enable SkillsMP (Remote Templates)? [Current: {config.skills_mp.enabled}]", default=config.skills_mp.enabled):
        config.skills_mp.enabled = True
        current_key = config.skills_mp.api_key or ""
        if not current_key or Confirm.ask("Update SkillsMP API Key?", default=False):
            config.skills_mp.api_key = Prompt.ask("SkillsMP API Key", password=True)
    else:
        config.skills_mp.enabled = False

    # Git
    if shutil.which("git"):
        config.git.auto_pr = Confirm.ask(
            f"Enable Auto-PR creation? [Current: {config.git.auto_pr}]",
            default=config.git.auto_pr
        )
    else:
        console.print("[yellow]⚠️ Git not found. Disabling Git features.[/yellow]")
        config.git.auto_pr = False

    # Scheduler
    config.scheduler.enabled = Confirm.ask(
        f"Enable Job Scheduler? [Current: {config.scheduler.enabled}]",
        default=config.scheduler.enabled
    )



    # Web UI
    console.print("\n[bold]Open WebUI Gateway[/bold]")
    if Confirm.ask(f"Enable Open WebUI Gateway? [Current: {config.webui.enabled}]", default=config.webui.enabled):
        config.webui.enabled = True
        config.webui.port = int(Prompt.ask("WebUI Port", default=str(config.webui.port)))
        config.webui.host = Prompt.ask("WebUI Host", default=config.webui.host)

        # Optional API Key
        current_api_key = config.webui.api_key or "None"
        if Confirm.ask(f"Set API Key? (Current: {current_api_key})", default=False):
             config.webui.api_key = Prompt.ask("API Key", password=True)
    else:
        config.webui.enabled = False


    # --- 5. Save & Wrap-up ---
    console.print("\n[bold green]💾 Saving Configuration...[/bold green]")

    if secrets:
        _save_env_file(secrets)

    try:
        config.save("config.json")
        console.print("[green]✅ Saved config.json[/green]")
    except Exception as e:
        console.print(f"[red]❌ Failed to save config.json: {e}[/red]")

    console.print(
        Panel.fit(
            "[bold blue]🎉 Setup Complete![/bold blue]\n\n"
            "Run [bold]python astra/main.py run[/bold] to start your bot."
        )
    )

if __name__ == "__main__":
    run_setup_wizard()
