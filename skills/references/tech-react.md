# React / React Native tech guide

## Component design checklist

- [ ] Single responsibility (a component does one thing)
- [ ] Props drilling (consider the Context API)
- [ ] Reusability
- [ ] Container vs Presentational separation

## State management

- [ ] Local state vs global state distinguished
- [ ] Unnecessary global state
- [ ] Immutability kept in state updates
- [ ] Correct useEffect dependency arrays
- [ ] Memory leaks (cleanup functions)

## Performance

- [ ] Unnecessary re-renders (React.memo, useMemo, useCallback)
- [ ] key prop used correctly (avoid using the index)
- [ ] Virtualization for large lists (react-window)
- [ ] Image optimization (lazy loading, WebP)
- [ ] Bundle size (code splitting)

## Type safety (TypeScript)

- [ ] No overuse of the any type
- [ ] Props types defined
- [ ] Optional chaining / nullish coalescing used
- [ ] Type guards used

## Hooks

- [ ] Rules of Hooks followed (call only at the top level)
- [ ] Custom hooks are appropriate
- [ ] useEffect cleanup functions
- [ ] Watch for overuse of useCallback/useMemo

## Test patterns

| Test type | Tool | Use |
|------------|------|------|
| Component test | Testing Library | UI rendering/interaction |
| Hook test | renderHook | Custom hooks |
| Async test | waitFor | API calls |
| Snapshot test | Jest snapshot | Detect UI changes |

## React Native additions

- [ ] Platform-specific code handling
- [ ] FlatList optimization (keyExtractor, getItemLayout)
- [ ] Image caching
- [ ] Native module usage patterns
- [ ] Responsive layout based on Dimensions

## Refactoring points

- **God component** → split into smaller components
- **Inline logic** → extract a custom Hook
- **Complex ternaries** → early return pattern
- **Props drilling** → Context or a state management library

## Project structure (typical)

```
src/
├── components/    # reusable components
├── pages/         # page components
├── hooks/         # custom hooks
├── api/           # API calls
├── store/         # state management
├── utils/         # utilities
└── types/         # TypeScript types
```
