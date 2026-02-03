# Configuration Guide

ASTra uses a layered configuration system with the following priority:

1. Environment variables (highest)
2. `config.json` file
3. Default values (lowest)

## Configuration File

Create `config.json` in the project root:

```json
{
  "orchestration": {
    "max_self_heal_attempts": 3,
    "global_timeout_seconds": 600,
    "test_timeout_seconds": 300,
    "allowed_users": ["123456789", "987654321"]
  },
  "llm": {
    "model": "ollama/qwen2.5-coder:7b",
    "host": "http://localhost:11434",
    "context_limit": 32000,
    "planning_model": null,
    "coding_model": null
  },
  "ingestion": {
    "embedding_model": "codebert",
    "ast_depth": 3,
    "safe_branches": ["main", "master"],
    "max_file_size_kb": 100,
    "batch_size": 50
  },
  "vectordb": {
    "persist_path": "./data/chromadb",
    "cleanup_threshold_days": 90
  },
  "knowledge_graph": {
    "enabled": true,
    "persist_path": "./data/knowledge_graph.graphml"
  }
}
```

## Environment Variables

All settings can be overridden via environment variables using the `ASTRA_` prefix and `__` for nesting:

```bash
# LLM Configuration
export ASTRA_LLM__MODEL="ollama/qwen2.5-coder:14b"
export ASTRA_LLM__HOST="http://localhost:11434"

# Orchestration
export ASTRA_ORCHESTRATION__GLOBAL_TIMEOUT_SECONDS=900
export ASTRA_ORCHESTRATION__MAX_SELF_HEAL_ATTEMPTS=5

# Discord
export DISCORD_TOKEN="your-bot-token"
```

## Configuration Sections

### Orchestration

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_self_heal_attempts` | int | 3 | Max retries before failing a task |
| `global_timeout_seconds` | int | 600 | Timeout for task execution |
| `test_timeout_seconds` | int | 300 | Timeout for test runs |
| `allowed_users` | list[str] | [] | Discord user IDs allowed to use commands |
| `fallback_to_cloud` | bool | false | Fall back to cloud LLM if local fails |

### LLM

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `model` | str | `ollama/qwen2.5-coder:7b` | Default LLM model |
| `host` | str | `http://localhost:11434` | Ollama/LLM server URL |
| `context_limit` | int | 32000 | Context window size |
| `planning_model` | str | null | Override model for planning (optional) |
| `coding_model` | str | null | Override model for coding (optional) |

### Ingestion

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `embedding_model` | str | `codebert` | Embedding model for vector search |
| `ast_depth` | int | 3 | AST parsing depth (1=signatures, 2=+docstrings, 3=full) |
| `safe_branches` | list[str] | ["main", "master"] | Branches safe for indexing |
| `max_file_size_kb` | int | 100 | Skip files larger than this |
| `batch_size` | int | 50 | Batch size for embedding operations |

### Embedding Models

| Name | Actual Model | Best For |
|------|-------------|----------|
| `codebert` | `microsoft/codebert-base` | Code search (default) |
| `mpnet` | `all-mpnet-base-v2` | General text |
| `default` | `all-MiniLM-L6-v2` | Fast, lightweight |

### Vector Database

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `persist_path` | str | `./data/chromadb` | Where to store vector data |
| `cleanup_threshold_days` | int | 90 | Delete stale collections after N days |

### Knowledge Graph

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | true | Enable knowledge graph features |
| `persist_path` | str | `./data/knowledge_graph.graphml` | Graph storage location |

## Security Configuration

### Allowed Users

By default, **no users can execute commands**. You must configure allowed users:

```json
{
  "orchestration": {
    "allowed_users": ["123456789012345678"]
  }
}
```

Or use the `/auth add @user` command from a pre-authorized user.

### Command Allowlist

Control which shell commands can be executed:

```json
{
  "orchestration": {
    "security": {
      "command_allowlist": ["git", "npm", "python", "pytest"],
      "require_permission_for_shell": true
    }
  }
}
```
