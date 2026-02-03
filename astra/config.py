"""Configuration loader with Pydantic validation."""

import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# --- Nested Configuration Models ---

class SecurityConfig(BaseModel):
    auto_install_packages: bool = False
    require_permission_for_shell: bool = True
    command_allowlist: list[str] = [
        "git", "npm", "node", "python", "pytest", "php", "composer", "cargo"
    ]
    admin_users: list[str] = []
    mfa_secrets: dict[str, str] = {}

class FallbackStrategy(BaseModel):
    mode: Literal["ask_user", "auto_escalate"] = "ask_user"
    escalation_model: str = "gpt-4o"
    api_key_env_var: str = "OPENAI_API_KEY"

class OrchestrationConfig(BaseModel):
    max_self_heal_attempts: int = 3
    log_ingestion_limit_kb: int = 50
    fallback_to_cloud: bool = False
    fallback_model: str | None = None
    temperature: float = 0.0
    resume_tasks: bool = True
    global_timeout_seconds: int = 600
    test_timeout_seconds: int = 300
    log_path: str = "./logs/astra.log"
    allowed_users: list[str] = []
    fallback_strategy: FallbackStrategy = Field(default_factory=FallbackStrategy)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    # Self-diagnosis options
    auto_fix_lint: bool = True  # Auto-fix linter issues when possible
    run_lint_before_test: bool = True  # Run linters before tests
    use_manifest_scripts: bool = True  # Use scripts from package.json/composer.json
    critic_enabled: bool = True # Enable/Disable critic loop
    critic_loops: int = 5  # Max turns for plan critique/refinement
    test_heuristics: dict[str, str] = {
        "npm": "npm test",
        "composer": "vendor/bin/phpunit",
        "python": "pytest",
        "cargo": "cargo test"
    }

class GitConfig(BaseModel):
    auto_pr: bool = True
    branch_prefix: str = "ai-dev-"
    review_required: bool = True

class IngestionConfig(BaseModel):
    ignore_patterns: list[str] = [
        ".env", "node_modules", "*.lock", "dist", "build", ".git", "vendor", "__pycache__"
    ]
    priority_files: list[str] = [
        "package.json", "composer.json", "tsconfig.json", "README.md", "Makefile"
    ]
    max_file_size_kb: int = 100
    embedding_model: str = "default"
    lazy_loading: bool = True
    batch_size: int = 50
    ast_depth: int = 3  # How deep to parse AST (1=signatures only, 2=+docstrings, 3=full)
    safe_branches: list[str] = ["main", "master"]

class LLMConfig(BaseModel):
    model: str = "ollama/qwen2.5-coder:7b"
    host: str = "http://localhost:11434"
    context_limit: int = 32000
    base_url: str | None = None
    planning_model: str | None = None
    coding_model: str | None = None
    critic_model: str | None = None

class VectorDBConfig(BaseModel):
    cleanup_threshold_days: int = 90
    persist_path: str = "./data/chromadb"
    backup_count: int = 2

class KnowledgeGraphConfig(BaseModel):
    enabled: bool = True
    persist_path: str = "./data/knowledge_graph.graphml"

class ProgressConfig(BaseModel):
    verbosity: str = "standard"
    update_interval_percent: int = 10

class ContextConfig(BaseModel):
    compression_enabled: bool = False
    compression_model: str = "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"
    target_token_count: int = 2000

class SkillsMPConfig(BaseModel):
    enabled: bool = False
    api_key: str | None = None
    cache_expiry_hours: int = 24
    endpoint: str = "https://skillsmp.com/api/v1"

class SchedulerConfig(BaseModel):
    enabled: bool = True
    db_path: str = "./data/scheduler.db"
    resource_guard_enabled: bool = True
    max_memory_percent: int = 90
    misfire_grace_time: int = 3600  # 1 hour
    coalesce: bool = True


# --- Main Settings Class ---

class Config(BaseSettings):
    """Application configuration."""

    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    vectordb: VectorDBConfig = Field(default_factory=VectorDBConfig)
    knowledge_graph: KnowledgeGraphConfig = Field(default_factory=KnowledgeGraphConfig)
    progress: ProgressConfig = Field(default_factory=ProgressConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    skills_mp: SkillsMPConfig = Field(default_factory=SkillsMPConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)

    model_config = SettingsConfigDict(
        env_prefix="ASTra_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore"
    )

    # --- Backward Compatibility API ---

    def get(self, *keys: str, default: Any = None) -> Any:
        """Retrieve nested value by keys, e.g. get('llm', 'model')."""
        val = self
        try:
            for k in keys:
                if isinstance(val, BaseModel):
                    val = getattr(val, k)
                elif isinstance(val, dict):
                    val = val[k]
                else:
                    return default
            return val
        except (AttributeError, KeyError):
            return default

    def is_command_allowed(self, command: str) -> bool:
        """Check if a command is in the allowlist."""
        return command in self.orchestration.security.command_allowlist

    def add_allowed_command(self, command: str) -> None:
        """Add a command to the allowlist."""
        allowlist = self.orchestration.security.command_allowlist
        if command not in allowlist:
            allowlist.append(command)
            # No need to call set(), list is mutable reference

    @property
    def allowed_users(self) -> list[str]:
         # Wrap nested list to match legacy interface if property access overrides field
         return self.orchestration.allowed_users

    @property
    def max_retries(self) -> int:
        return self.orchestration.max_self_heal_attempts

    @property
    def branch_prefix(self) -> str:
        return self.git.branch_prefix

    @classmethod
    def load(cls, path: str | Path = "config.json") -> "Config":
        """Load from JSON file (legacy support) and merge with env vars."""
        path_obj = Path(path)
        json_data = {}
        if path_obj.exists():
            import json
            try:
                text = path_obj.read_text(encoding="utf-8")
                json_data = json.loads(text)
            except Exception as e:
                logger.warning(f"Failed to load config file: {e}")

        return cls(**json_data)

    def save(self, path: str | Path = "config.json") -> None:
        """Save current configuration to a JSON file."""
        import json
        path_obj = Path(path)
        try:
            # model_dump() gives us a serializable dict from Pydantic V2
            data = self.model_dump()
            path_obj.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info(f"Configuration saved to {path}")
        except Exception as e:
            logger.error(f"Failed to save configuration to {path}: {e}")
            raise

# Global Accessor
_config: Config | None = None

def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.load()
    return _config

def reload_config() -> Config:
    global _config
    _config = Config.load()
    return _config
