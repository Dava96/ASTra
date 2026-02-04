import asyncio
from pathlib import Path

from astra.core.architecture import ArchitectureGenerator


async def verify_arch_generation():
    project_path = r"c:\Users\David\Desktop\Projects and Ideas\Code\Antigravity\ASTra\repos\osrs-progress-lambda"

    # 1. Ensure clean slate
    astra_dir = Path(project_path) / ".astra"
    arch_file = astra_dir / "ARCHITECTURE.md"
    if arch_file.exists():
        print(f"Deleting existing {arch_file}")
        arch_file.unlink()

    # 2. Run generation
    print("Generating ARCHITECTURE.md...")
    gen = ArchitectureGenerator()
    await gen.generate_if_missing(project_path)

    # 3. Verify
    if arch_file.exists():
        print(f"SUCCESS: {arch_file} created.")
        print(f"Size: {arch_file.stat().st_size} bytes")
    else:
        print(f"FAILURE: {arch_file} not found.")

if __name__ == "__main__":
    asyncio.run(verify_arch_generation())
