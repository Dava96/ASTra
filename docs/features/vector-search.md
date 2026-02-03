# Vector Search

ASTra uses semantic vector search powered by ChromaDB and sentence transformers to find relevant code snippets based on natural language queries.

## How It Works

1. **Indexing**: Code is parsed into AST nodes (functions, classes, etc.)
2. **Embedding**: Each node is embedded using CodeBERT
3. **Storage**: Embeddings are stored in ChromaDB
4. **Query**: Natural language queries are embedded and matched

```
User Query: "How do I authenticate users?"
         ↓
    [Embed Query]
         ↓
    [Vector Search]
         ↓
Results: auth.py:login(), middleware.py:verify_token(), ...
```

## Embedding Models

| Model | Config Value | Description |
|-------|-------------|-------------|
| CodeBERT | `codebert` | Best for code (default) |
| MPNet | `mpnet` | General purpose |
| MiniLM | `default` | Fast, lightweight |

Configure in `config.json`:

```json
{
  "ingestion": {
    "embedding_model": "codebert"
  }
}
```

## Indexing a Repository

### Via Discord

```
/checkout https://github.com/owner/repo
```

### Programmatic

```python
from astra.adapters.chromadb_store import ChromaDBStore
from astra.ingestion.parser import ASTParser

parser = ASTParser()
store = ChromaDBStore()

# Parse and index
for node in parser.parse_directory("./my-project"):
    store.upsert("my_project", [node])
```

## Querying

```python
from astra.adapters.chromadb_store import ChromaDBStore

store = ChromaDBStore()
results = store.query(
    collection="my_project",
    query="error handling middleware",
    n_results=10
)

for result in results:
    print(f"{result.node.file_path}:{result.node.start_line}")
    print(result.node.content[:200])
```

## AST Depth Configuration

Control how much code detail is indexed:

| Depth | Includes |
|-------|----------|
| 1 | Function/class signatures only |
| 2 | Signatures + docstrings |
| 3 | Full function/class bodies (default) |

```json
{
  "ingestion": {
    "ast_depth": 3
  }
}
```

## Language Support

The AST parser supports:

| Language | Extensions |
|----------|-----------|
| TypeScript | .ts, .tsx |
| JavaScript | .js, .jsx, .mjs, .cjs |
| Python | .py |
| PHP | .php |
| Go | .go |
| Rust | .rs |
| Ruby | .rb |

## Manifest File Detection

When querying, ASTra automatically includes relevant manifest files in the context:

| Language | Manifest Files |
|----------|---------------|
| JavaScript/TypeScript | package.json, tsconfig.json |
| PHP | composer.json |
| Python | pyproject.toml, requirements.txt |
| Go | go.mod |
| Rust | Cargo.toml |

This prevents the LLM from hallucinating dependencies that don't exist.

## Performance Tuning

### Batch Size

Control how many nodes are embedded at once:

```json
{
  "ingestion": {
    "batch_size": 50
  }
}
```

### Max File Size

Skip large files that are unlikely to be useful:

```json
{
  "ingestion": {
    "max_file_size_kb": 100
  }
}
```

### Ignore Patterns

Exclude files from indexing:

```json
{
  "ingestion": {
    "ignore_patterns": [
      "node_modules", "vendor", ".git", "dist", "build"
    ]
  }
}
```

## Cleanup

ChromaDB collections are automatically cleaned up after a configurable period:

```json
{
  "vectordb": {
    "cleanup_threshold_days": 90
  }
}
```

## Debugging

Check what's indexed in a collection:

```python
store = ChromaDBStore()
stats = store.get_stats()
print(f"Collections: {stats}")
```
