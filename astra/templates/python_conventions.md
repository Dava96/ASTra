# Python Development Conventions

## Type Safety
-   **Strict Typing**: Use type hints for all function arguments and return values.
-   **Pydantic**: Use Pydantic models for data structures and validation.
-   **No `Any`**: Avoid `Any` where possible. Use `Generic` or specific protocols.

## Testing
-   **Pytest**: Use `pytest` for all testing.
-   **Async**: Use `pytest-asyncio` for async tests.
-   **Mocking**: specificy `top-level` mocks where possible to avoid import side-effects.

## Libraries
-   **HTTP**: Prefer `httpx` over `requests` for async support.
-   **Path Handling**: Always use `pathlib.Path`, never `os.path`.

## Style
-   Follow PEP 8.
-   Use descriptive variable names.
-   Docstrings for all public modules, classes, and functions (Google style).
