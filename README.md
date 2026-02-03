# 🤖 ASTra - Autonomous AI Coding Agent

ASTra (Autonomous AI Coding Agent) is a powerful, self-hosted AI pair programmer designed to maintain and develop multi-language codebases. By combining **AST-based ingestion**, **Semantic Search**, and **Knowledge Graph relationships**, ASTra understands your code better than a simple text-based search.

---

## 🚀 Features

*   🤖 **Autonomous Coding**: Implements features and fixes bugs automatically using local or cloud LLMs.
*   🌳 **AST-Based Context**: Leverages `tree-sitter` to parse code into granular nodes (functions, classes, imports).
*   📊 **Knowledge Graph**: Tracks dependencies and relationships using `networkx`, enabling impact analysis and deep context retrieval.
*   🔍 **Semantic Search**: Uses `ChromaDB` with `CodeBERT` embeddings for high-accuracy code retrieval.
*   💬 **Discord Interface**: Command and control your agent via a sleek Discord bot interface.
*   🔄 **Self-Healing**: Automatically detects linting or test failures and iterates until a task is successful.

---

## 🛠 Prerequisites

*   **Python 3.12+** (Required)
*   **[uv](https://github.com/astral-sh/uv)** (Highly recommended for dependency management)
*   **[Ollama](https://ollama.ai/)** (For local LLM support)
*   **Discord Bot Token** (For the bot interface)
*   **8GB+ RAM** (Recommended for local embedding and inference)

---

## 📥 Installation & Setup

### 1. Clone the Repository
```powershell
git clone https://github.com/yourusername/ASTra.git
cd ASTra
```

### 2. Install Dependencies
Using `uv` (recommended):
```powershell
uv sync
```
Or using `pip`:
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install .
```

### 3. Interactive Configuration
ASTra includes a wizard to help you set up your `.env` and `config.json` files automatically:
```powershell
python -m astra.setup_wizard
```
The wizard will prompt you for:
*   `DISCORD_TOKEN`: Your bot token from the Discord Developer Portal.
*   `Admin User ID`: Your Discord user ID for security.
*   `LLM Provider`: Choose between `ollama` (local) or `openai` (cloud).
*   `Model Name`: e.g., `qwen2.5-coder:7b` for Ollama or `gpt-4o` for OpenAI.

---

## 💬 Discord Commands

ASTra is primarily controlled via Discord slash commands. Below is a comprehensive list of available commands:

### 🛠 Core Commands
| Command | Description |
|---------|-------------|
| `/feature <request>` | Implement a new feature in the current project. |
| `/fix <description>` | Fix a bug or issue in the codebase. |
| `/quick <file> <change>` | Apply a specific, small change to a single file. |
| `/checkout <repo>` | Clone and index a new repository for work. |
| `/screenshot <url>` | Capture a screenshot of a webpage (uses Playwright). |

### 📊 System & Task Management
| Command | Description |
|---------|-------------|
| `/status` | View the current task queue and system health. |
| `/cancel` | Terminate the currently running task. |
| `/last` | Detailed results of the most recently completed task. |
| `/history [limit]` | View the history of previous tasks (default: 5). |
| `/approve <task_id>` | Approve a pending task or implementation plan. |
| `/revise <task_id> <feedback>` | Request revisions on a task with specific feedback. |

### ⚙️ Configuration & Admin
| Command | Description |
|---------|-------------|
| `/config list` | List all current system configuration settings. |
| `/config get <key>` | Retrieve the value of a specific configuration key. |
| `/model current` | Show the LLM model currently in use. |
| `/model set <model> [target]` | Change the LLM (target: planning or coding). |
| `/auth add/remove/list` | Manage user access controls (Admin only). |
| `/cleanup [max_age_days]` | Remove stale indexed data (Admin only). |
| `/help` | Display the interactive help menu. |

---

## 🏗 Core Workflows

### 1. Codebase Ingestion 🗃️
Before ASTra can work on your code, it needs to index it. This process creates the Knowledge Graph and Vector Database.
```powershell
python -m astra.main ingest
```
*   **Parser**: Scans your project and extracts AST nodes.
*   **Vector DB**: Stores embeddings in `./data/chromadb`.
*   **Knowledge Graph**: Resolves dependencies and saves to `./data/knowledge_graph.graphml`.

### 2. Development (Discord Bot) 🤖
Once indexed, start the Discord service to interact with ASTra:
```powershell
python -m astra.main run
```

### 3. Knowledge Retrieval Logic
You can manually test context retrieval using the query script:
```powershell
python scripts/query_chroma.py path/to/file.py --context
```
This utility uses the Knowledge Graph to find dependencies and includes them in the AI's context window.

---

## 📂 Project Architecture

*   `astra/adapters/`: External service implementations (Discord, ChromaDB).
*   `astra/core/`: Orchestration logic and LLM client.
*   `astra/ingestion/`: The heart of ASTra; Parser, Dependency Resolver, and Knowledge Graph.
*   `astra/interfaces/`: Abstract base classes for extensibility.
*   `astra/tools/`: Powerful utilities for Git, Shell, and Browser operations.

---

## 🧪 Testing

ASTra uses `pytest` for verification. We maintain a high standard for integration and end-to-end reliability.

```powershell
# Run smoke tests
python -m pytest tests/test_smoke.py

# Run full integration tests (covers Ingestion -> Storage -> Relationships)
python -m pytest tests/test_full_integration.py
```

---

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.
