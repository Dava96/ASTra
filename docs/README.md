# ASTra Documentation

Welcome to ASTra - an AI-powered development assistant that uses vector search, knowledge graphs, and LLM orchestration to help you build software faster.

## Quick Start

1. Configure your environment (see [Configuration](configuration.md))
2. Start the Discord bot: `uv run python -m astra`
3. Use `/checkout <repo-url>` to index a repository
4. Ask questions or request features with `/ask` or `/feature`

## Features

### Core Capabilities

- **[Vector Search](features/vector-search.md)** - Semantic code search using CodeBERT embeddings
- **[Knowledge Graph](features/knowledge-graph.md)** - Dependency tracking and impact analysis
- **[RAG-First Planning](features/rag-first.md)** - Context-aware task planning

### Tools

- **[Custom Tools](features/custom-tools.md)** - Define your own tools via YAML
- **[PR Review](features/pr-review.md)** - Automated pull request analysis
- **[Git Operations](features/git-ops.md)** - Branch management and PR creation

### Configuration

- **[Configuration Guide](configuration.md)** - All configuration options
- **[Security](security.md)** - User authorization and safe practices

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Discord Gateway                       │
│              (User Commands & Responses)                 │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                     Orchestrator                         │
│    (Task Planning, Tool Execution, LLM Coordination)    │
└─────────────────────────────────────────────────────────┘
        │              │                │
        ▼              ▼                ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Vector Store│ │  Knowledge  │ │    Tools    │
│  (ChromaDB) │ │    Graph    │ │  Registry   │
└─────────────┘ └─────────────┘ └─────────────┘
```

## Directory Structure

```
astra/
├── adapters/       # External service adapters (Discord, ChromaDB)
├── core/           # Core logic (Orchestrator, LLM Client, Task Queue)
├── handlers/       # Command handlers
├── ingestion/      # Code parsing and indexing
├── interfaces/     # Protocol definitions
├── templates/      # Prompt templates
└── tools/          # Agent tools (Git, Knowledge, Aider, Custom)
```
