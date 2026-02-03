"""Generate architecture documentation for ASTra itself."""

import asyncio
import logging
import os

from astra.core.architecture import ArchitectureGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)

async def main():
    root_dir = os.getcwd()
    print(f"Generating architecture for: {root_dir}")

    generator = ArchitectureGenerator()

    # We force regeneration even if it exists, to test the new template
    # Since generate_if_missing only runs if missing, we will delete it first if it exists
    arch_file = os.path.join(root_dir, "ARCHITECTURE.md")
    if os.path.exists(arch_file):
        print("Removing existing ARCHITECTURE.md to force regeneration...")
        os.remove(arch_file)

    await generator.generate_if_missing(root_dir)
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
