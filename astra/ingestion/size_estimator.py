import contextlib
import logging
import random
from pathlib import Path
from typing import Any

from astra.ingestion.parser import ASTParser

logger = logging.getLogger(__name__)

class SizeEstimator:
    """
    Estimates the ingestion size (node count, vector DB size)
    by sampling a subset of the codebase.
    """

    def __init__(self):
        self.parser = ASTParser()

    def estimate(
        self,
        directory: str | Path,
        sample_rate: float = 0.05,
        ast_depth: int = 3
    ) -> dict[str, Any]:
        """
        Run the estimation.

        Args:
            directory: Project root.
            sample_rate: Fraction of files to sample (0.0 to 1.0).
            ast_depth: Granularity level.

        Returns:
            Dictionary with projections.
        """
        directory = Path(directory)
        all_files = []

        # 1. Collect all valid files
        # We manually walk to avoid the generator overhead of parse_directory for this purpose
        import os

        from astra.ingestion.parser import get_language_for_file

        total_size_bytes = 0

        for root, dirs, files in os.walk(directory):
            # Skip common ignore dirs
            if any(p in str(Path(root)) for p in [".git", "__pycache__", "node_modules", ".venv", "env"]):
                dirs[:] = []
                continue

            for file in files:
                fp = Path(root) / file
                if get_language_for_file(fp):
                    all_files.append(fp)
                    with contextlib.suppress(BaseException):
                        total_size_bytes += fp.stat().st_size

        total_files = len(all_files)
        if total_files == 0:
            return {"error": "No ingestible files found."}

        # 2. Sample
        sample_size = max(1, int(total_files * sample_rate))
        # Cap sample size to avoid taking too long on massive repos
        sample_size = min(sample_size, 50)

        sampled_files = random.sample(all_files, sample_size)

        # 3. Parse Samples
        total_nodes = 0
        parsed_bytes = 0

        for fp in sampled_files:
            try:
                nodes = self.parser.parse_file(fp, relative_to=directory, ast_depth=ast_depth)
                total_nodes += len(nodes)
                parsed_bytes += fp.stat().st_size
            except Exception:
                pass

        if parsed_bytes == 0:
            return {"error": "Failed to parse any sampled files."}

        # 4. Extrapolate
        # Ratio: Nodes per Byte
        nodes_per_byte = total_nodes / parsed_bytes

        projected_total_nodes = int(nodes_per_byte * total_size_bytes)

        # Rough vector DB size estimation
        # Assuming avg embedding + metadata overhead is ~4KB per node (very rough)
        est_db_size_mb = (projected_total_nodes * 4) / 1024

        return {
            "total_files": total_files,
            "total_size_mb": round(total_size_bytes / (1024*1024), 2),
            "sample_size": sample_size,
            "sample_nodes": total_nodes,
            "projected_nodes": projected_total_nodes,
            "projected_db_size_mb": round(est_db_size_mb, 2),
            "nodes_per_kb": round(nodes_per_byte * 1024, 2)
        }
