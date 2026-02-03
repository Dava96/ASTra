# Custom Tools

ASTra allows you to define custom tools via YAML files without writing any Python code. Custom tools execute shell commands with parameter substitution.

## Quick Start

1. Create a YAML file in `tools/custom/`:

```yaml
# tools/custom/deploy.yaml
name: deploy_staging
description: Deploy to staging server
command: ssh deploy@staging ./deploy.sh {branch}
parameters:
  branch:
    type: string
    description: Branch to deploy
    required: true
```

2. Restart ASTra - the tool will be automatically loaded.

3. The LLM can now use this tool during task execution.

## YAML Format

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique tool identifier (used by LLM) |
| `description` | string | What the tool does (shown to LLM) |
| `command` | string | Shell command to execute |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `parameters` | object | Parameter definitions |

### Parameter Definition

```yaml
parameters:
  param_name:
    type: string|integer|boolean
    description: What this parameter is for
    required: true|false
```

## Parameter Substitution

Use `{param_name}` in the command string. Parameters are substituted before execution:

```yaml
name: run_tests
description: Run tests for a specific module
command: pytest tests/{module} -v
parameters:
  module:
    type: string
    description: Module name to test
    required: true
```

When called with `module="auth"`, executes: `pytest tests/auth -v`

## Examples

### Git Operations

```yaml
# tools/custom/git_sync.yaml
name: git_sync
description: Sync with remote repository
command: git fetch origin && git rebase origin/{branch}
parameters:
  branch:
    type: string
    description: Branch to sync with
    required: true
```

### Docker Compose

```yaml
# tools/custom/docker_restart.yaml
name: restart_service
description: Restart a Docker Compose service
command: docker compose restart {service}
parameters:
  service:
    type: string
    description: Service name from docker-compose.yml
    required: true
```

### Database Migrations

```yaml
# tools/custom/migrate.yaml
name: run_migrations
description: Run database migrations
command: php artisan migrate --force
parameters: {}
```

### NPM Scripts

```yaml
# tools/custom/npm_script.yaml
name: npm_run
description: Run an npm script
command: npm run {script}
parameters:
  script:
    type: string
    description: Script name from package.json
    required: true
```

## Security Considerations

> ⚠️ **Warning**: Custom tools execute shell commands with the same permissions as ASTra. Be careful about:
> - Commands that modify system state
> - Commands with unsanitized user input
> - Commands that access sensitive data

### Best Practices

1. **Limit scope**: Make tools specific, not general-purpose
2. **Validate inputs**: Use specific parameter types
3. **Avoid secrets**: Don't embed passwords in commands
4. **Log execution**: Commands are logged for audit

## Loading Custom Tools

Tools are loaded from `tools/custom/` at startup. To reload without restarting:

```python
from astra.tools.custom_loader import load_custom_tools

tools = load_custom_tools("tools/custom")
for tool in tools:
    orchestrator._tools.register(tool)
```

## Debugging

Enable debug logging to see custom tool loading:

```bash
export ASTRA_LOG_LEVEL=DEBUG
```

Logs will show:
```
INFO: Loaded custom tool: deploy_staging from tools/custom/deploy.yaml
```
