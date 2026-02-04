import os


def bundle_astra(root_dir="."):
    output_file = "ASTRA_CONTEXT.md"

    # Folders that must be COMPLETELY ignored
    forbidden = {
        ".venv", "venv", "env", ".git", "__pycache__",
        "node_modules", "data", "logs", "chromadb", "screenshots", "MagicMock"
    }

    # Specific files to skip
    ignored_files = {output_file, "uv.lock", ".aider.input.history", ".aider.chat.history.md"}

    print("🚀 Starting High-Signal Bundle...")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# ASTRA PROJECT CONTEXT\n\n")

        for root, dirs, files in os.walk(root_dir):
            # 1. Standard os.walk pruning (stops it from entering folders)
            dirs[:] = [d for d in dirs if d not in forbidden]

            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, root_dir)

                # 2. Hard string check as a fail-safe
                if any(ext in rel_path.split(os.sep) for ext in forbidden):
                    continue

                if file in ignored_files or file.startswith('.'):
                    continue

                # 3. Only grab the high-value logic files
                if file.endswith((".py", ".md", ".graphml", ".toml", ".json", ".yaml")):
                    print(f"  + Adding: {rel_path}")
                    f.write(f"\n## FILE: {rel_path}\n```python\n")

                    try:
                        with open(full_path, encoding="utf-8", errors="ignore") as code:
                            f.write(code.read())
                    except Exception as e:
                        f.write(f"Error reading {rel_path}: {e}")
                    f.write("\n```\n---\n")

    size_kb = os.path.getsize(output_file) / 1024
    print(f"\n✅ Done! Context saved to {output_file} ({size_kb:.2f} KB)")

if __name__ == "__main__":
    bundle_astra()
