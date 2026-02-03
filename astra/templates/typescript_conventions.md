# TypeScript Development Conventions

## Type Safety
-   **Strict Mode**: Ensure `strict: true` in `tsconfig.json`.
-   **No Explicit `any`**: Use `unknown` or narrow types instead.
-   **Interfaces vs Types**: Prefer `interface` for public APIs, `type` for unions/intersections.

## Testing
-   **Framework**: Use `Vitest` (preferred) or `Jest`.
-   **Testing Library**: Use `@testing-library/react` for components.

## Modern JS/TS
-   Use ES6+ features (destructuring, spread, async/await).
-   Prefer `const` over `let`. Never use `var`.
-   Use Optional Chaining (`?.`) and Nullish Coalescing (`??`).

## Async
-   Always use `async/await` over raw Promises `.then()`.
-   Handle errors with `try/catch`.
