# FastAPI Framework Rules

## Structure
-   Use `APIRouter` for modular route definition.
-   Separate `schemas` (Pydantic), `models` (DB), and `routers` (Endpoints).

## Dependency Injection
-   Use `Depends()` for all shared logic (DB sessions, auth, config).
-   Keep dependencies lightweight.

## Error Handling
-   Use `HTTPException` for expected errors.
-   Raise exceptions, don't return error objects.

## Async
-   Define *path operation functions* with `async def`.
-   Ensure blocking I/O is run in a threadpool (or use async drivers).
