# Knowledge Graph

ASTra builds a Knowledge Graph of your codebase to track dependencies, analyze impact, and provide intelligent context to the LLM.

## Overview

The Knowledge Graph stores:

- **Nodes**: Functions, classes, interfaces, modules
- **Edges**: Import relationships, function calls, inheritance

```
┌────────────┐    imports    ┌────────────┐
│  auth.py   │ ────────────► │  utils.py  │
│ └─login()  │               │ └─hash()   │
└────────────┘               └────────────┘
      │                            │
      │ calls                      │ calls
      ▼                            ▼
┌────────────┐               ┌────────────┐
│ db.py      │               │ crypto.py  │
│ └─query()  │               │ └─encrypt()│
└────────────┘               └────────────┘
```

## Features

### Dependency Analysis

Find what a file depends on:

```python
from astra.ingestion.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph()
kg.load("./data/knowledge_graph.graphml")

deps = kg.get_dependencies("src/auth.py")
# ['src/utils.py', 'src/db.py', 'src/crypto.py']
```

### Impact Analysis

Find what would be affected by changing a file:

```python
dependents = kg.get_dependents("src/utils.py")
# ['src/auth.py', 'src/api.py', 'src/handlers/users.py']
```

### Statistics

Get an overview of the codebase structure:

```python
stats = kg.get_stats()
# {
#     'total_nodes': 150,
#     'total_edges': 230,
#     'languages': {'python': 80, 'typescript': 70},
#     'node_types': {'function': 100, 'class': 50}
# }
```

## Building the Graph

### During Checkout

The Knowledge Graph is automatically built when you run `/checkout`:

```
/checkout https://github.com/owner/repo
```

### Programmatic

```python
from astra.ingestion.parser import ASTParser
from astra.ingestion.knowledge_graph import KnowledgeGraph

parser = ASTParser()
kg = KnowledgeGraph()

for node in parser.parse_directory("./my-project"):
    kg.add_node(
        id=node.id,
        type=node.type,
        name=node.name,
        file_path=node.file_path
    )
    # TODO: Add edges for imports/calls

kg.save("./data/knowledge_graph.graphml")
```

## Configuration

```json
{
  "knowledge_graph": {
    "enabled": true,
    "persist_path": "./data/knowledge_graph.graphml"
  }
}
```

## Query Types

### Via Discord

```
# Get dependencies
/ask What files does auth.py depend on?

# Get impact analysis
/ask What would be affected if I change utils.py?
```

### Via Knowledge Tool

The `query_knowledge_graph` tool is available to the LLM:

```python
# Tool definitions registered automatically
tool_defs = orchestrator._tools.get_definitions()
# Includes query_knowledge_graph with:
#   - "dependencies" query type
#   - "impact" query type
#   - "stats" query type
```

## Storage Format

The Knowledge Graph is stored as GraphML, a standard XML format:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<graphml>
  <graph id="KnowledgeGraph">
    <node id="src/auth.py:login:10">
      <data key="type">function</data>
      <data key="name">login</data>
      <data key="file_path">src/auth.py</data>
    </node>
    <edge source="src/auth.py:login:10" target="src/utils.py:hash:5">
      <data key="type">calls</data>
    </edge>
  </graph>
</graphml>
```

## Integration with RAG

The Knowledge Graph is used during RAG-First planning:

1. Vector search finds relevant code snippets
2. For the top result, KG queries find dependencies
3. All context is provided to the LLM

```python
# In Orchestrator._gather_context()
if results:
    top_file = results[0].node.file_path
    kg_tool = self._tools.get("query_knowledge_graph")
    deps = await kg_tool.execute("dependencies", target=top_file)
    impact = await kg_tool.execute("impact", target=top_file)
```

## Limitations

- Import/call relationship extraction is language-dependent
- Dynamic imports may not be detected
- Large codebases may have slow traversal
