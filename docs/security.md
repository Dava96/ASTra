# Security

ASTra takes security seriously. This document covers authorization, safe practices, and configuration.

## User Authorization

### Default Behavior

**By default, no users can execute commands.** The `allowed_users` list must be configured.

```python
# In discord_gateway.py
def is_user_authorized(self, user_id: str) -> bool:
    allowed = self._config.allowed_users
    if not allowed:
        return False  # Deny all if list is empty
    return user_id in allowed
```

### Configuring Allowed Users

#### Via config.json

```json
{
  "orchestration": {
    "allowed_users": ["123456789012345678", "987654321098765432"]
  }
}
```

#### Via Discord Commands

An authorized user can add others:

```
/auth add @username
/auth remove @username
/auth list
```

### Finding Your Discord User ID

1. Enable Developer Mode in Discord Settings
2. Right-click your username → Copy ID

## Command Security

### Authorization is Checked Everywhere

Every Discord command checks authorization:

```python
@app_commands.command()
async def feature(self, interaction):
    if not self.is_user_authorized(str(interaction.user.id)):
        await interaction.response.send_message("❌ Not authorized")
        return
    # ... handle command
```

### Shell Command Allowlist

Control which shell commands can be executed:

```json
{
  "orchestration": {
    "security": {
      "command_allowlist": ["git", "npm", "python", "pytest", "php", "composer"],
      "require_permission_for_shell": true
    }
  }
}
```

## Safe Indexing

### Branch Restriction

Only safe branches are indexed to prevent exposure of sensitive feature branches:

```json
{
  "ingestion": {
    "safe_branches": ["main", "master"]
  }
}
```

If you checkout a non-safe branch:

```
⚠️ Clone successful, but indexing skipped.
Branch `feature/secret` is not in safe list ["main", "master"].
Switch to a safe branch to build the Knowledge Graph.
```

### File Exclusions

Sensitive files are excluded by default:

```json
{
  "ingestion": {
    "ignore_patterns": [".env", "*.key", "*.pem", "secrets/"]
  }
}
```

## Token Management

### GitHub Personal Access Token

Store securely:

```bash
export GITHUB_TOKEN="ghp_xxxx"
```

Never commit tokens to the repository.

### Discord Bot Token

```bash
export DISCORD_TOKEN="your-bot-token"
```

## LLM Security

### Local-First

By default, ASTra uses local Ollama models:

```json
{
  "llm": {
    "model": "ollama/qwen2.5-coder:7b",
    "host": "http://localhost:11434"
  }
}
```

### Cloud Fallback

Cloud fallback is **disabled by default**:

```json
{
  "orchestration": {
    "fallback_to_cloud": false
  }
}
```

If enabled, ensure you trust the cloud provider with your code context.

## Custom Tool Security

### Risks

Custom tools execute shell commands. Be aware of:

- **Command injection**: Unsanitized parameters
- **Privilege escalation**: Running as current user
- **Data exposure**: Commands may access sensitive files

### Best Practices

1. **Validate parameters**: Use specific types
2. **Limit scope**: Make tools specific, not general
3. **Audit logs**: Commands are logged
4. **Review YAML files**: Treat as code

Example of a safe tool:

```yaml
name: run_tests
description: Run test suite
command: pytest tests/ -v
parameters: {}  # No user input
```

Example of a risky tool:

```yaml
name: run_command
description: Run any command
command: {cmd}  # DANGER: Arbitrary execution
parameters:
  cmd:
    type: string
```

## Audit Logging

All commands and tool executions are logged:

```
INFO: User 123456789 executed /checkout https://github.com/owner/repo
INFO: Executing custom tool 'deploy_staging' with args: {'branch': 'main'}
```

Configure log path:

```json
{
  "orchestration": {
    "log_path": "./logs/astra.log"
  }
}
```

## Recommendations

1. **Use local LLMs** for sensitive codebases
2. **Restrict allowed_users** to trusted developers
3. **Review custom tools** before deployment
4. **Enable safe_branches** for production
5. **Rotate tokens** regularly
6. **Monitor logs** for unusual activity
