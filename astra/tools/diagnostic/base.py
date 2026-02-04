"""Base class for output parsers."""

from abc import ABC, abstractmethod

from astra.tools.diagnostic.models import TestResult


class OutputParser(ABC):
    """Base class for output parsers.

    Subclasses must define:
    - name: Unique parser identifier
    - patterns: List of strings to detect this parser's format
    - parse(): Method to parse output into TestResult
    """

    name: str = ""
    patterns: list[str] = []

    def can_parse(self, output: str) -> bool:
        """Check if this parser can handle the given output."""
        output_lower = output.lower()
        return any(pattern.lower() in output_lower for pattern in self.patterns)

    @abstractmethod
    def parse(self, output: str) -> TestResult:
        """Parse output into structured TestResult."""
        pass
