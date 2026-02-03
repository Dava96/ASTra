# RAG-First Planning

ASTra uses a "RAG-First" approach to task planning, ensuring the LLM has access to relevant codebase context before generating implementation plans.

## Overview

RAG (Retrieval-Augmented Generation) First means:

1. **Retrieve** relevant context from Vector Store and Knowledge Graph
2. **Augment** the LLM prompt with this context
3. **Generate** a plan grounded in actual code

```
User Request: "Add authentication to the API"
         ↓
   [1. Retrieve Context]
   ├── Vector Search: auth.py, middleware.py, users.py
   ├── Knowledge Graph: auth.py → depends on → utils.py, db.py
   └── Manifests: package.json (shows JWT library exists)
         ↓
   [2. Augment Prompt]
   "Given the following codebase context: ... Plan how to add auth"
         ↓
   [3. Generate Plan]
   LLM creates plan using actual file names, existing patterns
```

## Why RAG-First?

### Without RAG

```
User: "Add auth"
LLM: "Create auth.js using passport.js..."
Reality: Project uses Python with FastAPI
```

### With RAG-First

```
User: "Add auth"
Context: Detected Python, FastAPI patterns, existing User model
LLM: "Extend existing User model in models/user.py, add FastAPI dependency..."
```

## Context Gathering

The `_gather_context` method collects three types of information:

### 1. Manifest Files (Dependency Context)

Prevents hallucination of non-existent packages:

```python
# Automatically detects and includes:
# - package.json for JS/TS projects
# - composer.json for PHP projects
# - pyproject.toml for Python projects
# - go.mod for Go projects
```

### 2. Vector Search (Code Snippets)

Finds semantically relevant code:

```python
results = self._vector_store.query(
    collection=collection,
    query=user_request,
    n_results=10
)
```

### 3. Knowledge Graph (Dependencies)

Provides structural understanding:

```python
deps = await kg_tool.execute("dependencies", target=top_file)
impact = await kg_tool.execute("impact", target=top_file)
```

## Context Format

The gathered context is formatted as Markdown:

```markdown
### Project Dependencies:
#### package.json
```json
{"name": "my-app", "dependencies": {"express": "^4.18.0"}}
```

### Relevant Code Snippets (Vector Search):
// File: src/auth.py:15
def login(username: str, password: str):
    user = db.get_user(username)
    ...

// File: src/middleware.py:8
def require_auth(func):
    ...

### Knowledge Graph Analysis for src/auth.py:
Dependencies: src/db.py, src/crypto.py
Impact: src/api.py, src/handlers/users.py
```

## Planning Prompts

The context is injected into planning prompts:

```python
prompt = self._templates.render(
    "planning_feature",
    request=context.task.request,
    context=retrieved_context  # RAG context here
)
```

## Tool-Augmented Planning

The planning phase can also use tools to gather more context:

```python
tool_defs = self._tools.get_definitions()
# Includes: search_code, query_knowledge_graph, read_file

response = await planning_llm.chat(messages, tools=tool_defs)
```

If the LLM needs more information, it can call tools:

```
LLM: I need to see the User model
Tool Call: read_file(path="models/user.py")
Tool Result: class User(Base): ...
LLM: Now I can plan the auth changes
```

## Configuration

### Context Limits

Control how much context is gathered:

```python
# In _gather_context
results = store.query(..., n_results=10)  # Top 10 snippets
manifest_content[:4000]  # Truncate large manifests
```

### LLM Context Window

Ensure context fits in the model's context window:

```json
{
  "llm": {
    "context_limit": 32000
  }
}
```

## Debugging

Enable debug logging to see gathered context:

```bash
export ASTRA_LOG_LEVEL=DEBUG
```

Logs will show:
```
DEBUG: Found manifest: package.json
DEBUG: Vector search returned 8 results
DEBUG: KG dependencies for src/auth.py: ['db.py', 'utils.py']
```

## Best Practices

1. **Keep repositories indexed**: Fresh indexes = better context
2. **Use descriptive requests**: "Add JWT auth to /api/users" > "Add auth"
3. **Review plans before approving**: RAG helps but isn't perfect
4. **Update manifests**: Accurate package.json = accurate suggestions
