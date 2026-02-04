import os


def bundle_astra(root_dir="."):
    output_file = "ASTRA_CONTEXT.md"

    # 1. Aggressive Ignore List
    ignored_parts = {
        ".venv", "venv", "env", "node_modules", ".git", ".pytest_cache",
        "__pycache__", "data", "logs", "screenshots", "chromadb", "MagicMock"
    }
    ignored_files = {output_file, "uv.lock", ".aider.input.history", ".aider.chat.history.md"}

    print("🚀 Bundling ASTRA (High-Signal Only)...")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# ASTRA PROJECT CONTEXT\n\n")

        for root, dirs, files in os.walk(root_dir):
            # 2. PRUNING: This prevents the script from even ENTERING .venv or .git
            dirs[:] = [d for d in dirs if d not in ignored_parts]

            # 3. FAIL-SAFE: If any part of the current path is in ignored_parts, skip it
            path_parts = set(os.path.normpath(root).split(os.sep))
            if any(p in ignored_parts for p in path_parts):
                continue

            for file in files:
                if file in ignored_files or file.startswith('.'):
                    continue

                # Focus on code and configs
                if file.endswith((".py", ".md", ".graphml", ".toml", ".json", ".yaml")):
                    path = os.path.join(root, file)
                    rel_path = os.path.relpath(path, root_dir)

                    print(f"  + {rel_path}")
                    f.write(f"\n## FILE: {rel_path}\n```python\n") # Assume python for highlighting

                    try:
                        with open(path, encoding="utf-8", errors="ignore") as code:
                            f.write(code.read())
                    except Exception as e:
                        f.write(f"Error reading: {e}")
                    f.write("\n```\n---\n")

    print(f"\n✅ Done! Check {output_file}. It should be much smaller now.")

if __name__ == "__main__":
    bundle_astra()
