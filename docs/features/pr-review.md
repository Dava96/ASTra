# PR Review

ASTra includes a PR Review tool that analyzes pull requests using the Knowledge Graph to identify high-impact changes and potential risks.

## Overview

The PR Review tool:

1. Fetches changed files from a PR
2. Queries the Knowledge Graph for each file's dependents
3. Identifies high-impact files (those with many dependents)
4. Generates risk assessments and recommendations

## Usage

### Via Discord Command

```
/review pr:42 repo:owner/repo
```

### Programmatic Use

```python
from astra.tools.pr_review import PRReviewTool
from astra.ingestion.knowledge_graph import KnowledgeGraph

# Initialize with Knowledge Graph
kg = KnowledgeGraph()
kg.load("./data/knowledge_graph.graphml")

tool = PRReviewTool(knowledge_graph=kg)

# Review a PR
result = await tool.execute(
    pr_number=42,
    repo="owner/repo"
)

print(result["summary"])
print(result["risks"])
print(result["recommendations"])
```

## Response Format

```python
{
    "pr_number": 42,
    "repo": "owner/repo",
    "summary": "Reviewed 5 changed files. Potential impact on 23 dependent files. Found 1 risks.",
    "risks": [
        {
            "severity": "high",
            "message": "2 files have high blast radius",
            "files": [
                {
                    "file": "src/core/utils.py",
                    "dependents": 15,
                    "examples": ["auth.py", "api.py", "models.py"]
                }
            ]
        }
    ],
    "recommendations": [
        "Consider breaking this PR into smaller changes",
        "Dependency changes detected - verify lock files are updated"
    ],
    "impact_analysis": {
        "changed_files": 5,
        "affected_dependents": 23,
        "high_impact_files": 2
    }
}
```

## Risk Detection

### High Impact Files

A file is considered "high impact" if it has **5 or more dependents** in the Knowledge Graph. These files require extra review attention.

### Automatic Recommendations

The tool automatically suggests:

| Condition | Recommendation |
|-----------|----------------|
| >10 affected dependents | "Consider breaking this PR into smaller changes" |
| package.json/composer.json changed | "Dependency changes detected - verify lock files are updated" |

## Knowledge Graph Integration

The PR Review tool queries the Knowledge Graph to find:

1. **Direct dependents**: Files that import/require the changed file
2. **Transitive impact**: Files affected by changes to dependencies

```
Changed: src/utils.py
    ↓ imported by
  src/api.py
    ↓ imported by
  src/handlers/auth.py
  src/handlers/users.py
```

## Configurationthe 

### High Impact Threshold

The default threshold of 5 dependents can be adjusted:

```python
# In pr_review.py
HIGH_IMPACT_THRESHOLD = 5  # Files with >= this many dependents
```

## Best Practices

1. **Index before reviewing**: Ensure the repository is indexed with `/checkout`
2. **Update Knowledge Graph**: Re-index after major refactors
3. **Review high-impact files carefully**: Changes to core utilities affect many files
4. **Watch for circular dependencies**: The KG can reveal dependency cycles

## Limitations

- Requires repository to be indexed
- Only analyzes direct code dependencies (not runtime)
- Cannot detect semantic changes (e.g., API contract changes)
