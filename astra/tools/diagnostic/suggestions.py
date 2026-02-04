"""Error pattern matching and suggestions."""

import re

# Use pre-compiled patterns for performance
# List of (CompiledRegex, SuggestionTemplate)
ERROR_PATTERNS = [
    (
        re.compile(r"ImportError: No module named ['\"]?(\S+)['\"]?", re.IGNORECASE),
        "Install missing package: pip install {1}",
    ),
    (
        re.compile(r"ModuleNotFoundError: No module named ['\"]?(\S+)['\"]?", re.IGNORECASE),
        "Install missing package: pip install {1}",
    ),
    (
        re.compile(r"SyntaxError: (.+)", re.IGNORECASE),
        "Check for missing brackets, quotes, or colons near the error",
    ),
    (
        re.compile(
            r"TypeError: (.+) takes (\d+) positional arguments? but (\d+) (?:was|were) given",
            re.IGNORECASE,
        ),
        "Function called with wrong number of arguments ({2} expected, {3} given)",
    ),
    (
        re.compile(
            r"AttributeError: ['\"]?(\S+)['\"]? object has no attribute ['\"]?(\S+)['\"]?",
            re.IGNORECASE,
        ),
        "Check if '{2}' exists on '{1}' or if it's a typo",
    ),
    (
        re.compile(r"NameError: name ['\"]?(\S+)['\"]? is not defined", re.IGNORECASE),
        "'{1}' is not defined - check imports or spelling",
    ),
    (
        re.compile(r"KeyError: ['\"]?(\S+)['\"]?", re.IGNORECASE),
        "Key '{1}' not found in dictionary - check key spelling or use .get()",
    ),
    (
        re.compile(r"IndentationError: (.+)", re.IGNORECASE),
        "Fix indentation - ensure consistent spaces/tabs",
    ),
    (
        re.compile(r"AssertionError: (.+)?", re.IGNORECASE),
        "Assertion failed - check expected vs actual values",
    ),
    # JavaScript/Node
    (
        re.compile(r"ReferenceError: (\S+) is not defined", re.IGNORECASE),
        "'{1}' is not defined - check imports or variable declarations",
    ),
    (
        re.compile(r"Cannot find module ['\"](\S+)['\"]", re.IGNORECASE),
        "Install missing package: npm install {1}",
    ),
    # Common Network/System
    (
        re.compile(r"ConnectionRefusedError: (.+)", re.IGNORECASE),
        "Connection refused - check if the service is running and port is correct",
    ),
    (
        re.compile(r"PermissionError: (.+)", re.IGNORECASE),
        "Permission denied - check file permissions or run as admin/root",
    ),
]


def get_suggestion(error_message: str) -> str:
    """Match error message to a suggestion."""
    for pattern, template in ERROR_PATTERNS:
        match = pattern.search(error_message)
        if match:
            suggestion = template
            # Substitute captured groups
            for i, group in enumerate(match.groups(), 1):
                suggestion = suggestion.replace(f"{{{i}}}", group or "")
            return suggestion
    return ""
