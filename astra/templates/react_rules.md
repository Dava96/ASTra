# React Framework Rules

## Components
-   **Functional Only**: Use functional components with Hooks. No Class components.
-   **PascalCase**: Filenames and Component names.

## State Management
-   Use `useState` for local state.
-   Use Context or external stores (Zustand/Redux) for global state. Avoid prop drilling > 2 levels.

## Hooks
-   Follow the Rules of Hooks (top level only).
-   Create custom hooks to extract complex logic.

## Performance
-   Use `useMemo` and `useCallback` judiciously (measure first).
-   Avoid defining functions/objects inside render loops unless necessary.
