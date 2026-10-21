# Automatic code style detection

Sample 3–5 existing files to learn the project's style patterns.
Follow the detected style 100%, and do not propose a new "better" way.

## Spring Boot

| Item | What to check |
|------|----------|
| **Naming** | `UserDto` vs `UserDTO` vs `UserRequest`/`UserResponse` |
| **Services** | Interface + implementation vs class only |
| **DI** | `@Autowired` vs `@RequiredArgsConstructor` |
| **Lombok** | `@Data` vs individual `@Getter/@Setter` |
| **Method names** | `getUser` vs `findUser` vs `retrieveUser` |
| **Packages** | By layer (`controller/service`) vs by feature (`user/order`) |
| **Return type** | `ResponseEntity` vs direct return |
| **Exception handling** | `@ControllerAdvice` + custom exception pattern |
| **Builder** | Whether the Builder pattern is used |

## React / React Native

| Item | What to check |
|------|----------|
| **Components** | `function Component()` vs `const Component = () => {}` |
| **Props types** | `interface` vs `type` |
| **Export** | `export default` vs named export |
| **File names** | `PascalCase.tsx` vs `kebab-case.tsx` |
| **Import order** | Grouping pattern |
| **Hook naming** | `use-` prefix rule |
| **Styling** | CSS Modules / Styled Components / Tailwind / Emotion |
| **State management** | Context / Redux / Zustand / Recoil |
| **Linter** | `.eslintrc`, `.prettierrc` rules |

### React Native additions

| Item | What to check |
|------|----------|
| **StyleSheet** | `StyleSheet.create` usage pattern |
| **Platform** | How platform-specific code is branched |
| **FlatList** | keyExtractor, getItemLayout patterns |

### React Native Expo additions

| Item | What to check |
|------|----------|
| **Routing** | `expo-router` vs `react-navigation` |
| **Config** | `app.json` / `app.config.js` pattern |
| **SDK** | API usage patterns per Expo SDK version |

## Flutter

| Item | What to check |
|------|----------|
| **File names** | Confirm snake_case |
| **Widget** | StatelessWidget vs StatefulWidget pattern |
| **State management** | Provider / Riverpod / Bloc / GetX |
| **const** | Whether const constructors are used |
| **Structure** | feature-first vs layer-first |
| **Lint** | `analysis_options.yaml` rules |

## Next.js

Everything in the **React / React Native** section above, plus:

| Item | What to check |
|------|----------|
| **Routing** | App Router vs Pages Router |
| **Data fetching** | Server Component / `getServerSideProps` / `fetch` cache |
| **Layout** | `layout.tsx` nesting pattern |

## Node.js / Python

| Item | What to check |
|------|----------|
| **Project structure** | By layer vs by feature |
| **Naming** | camelCase (Node) / snake_case (Python) |
| **Error handling** | Middleware / exception handler pattern |
| **Linter** | ESLint (Node) / ruff, black (Python) |

## Style principles

1. **Consistency > best practice** — the team convention comes first
2. **Follow detected patterns 100%** — down to variable names, method names, and import order
3. **Do not propose new approaches** — offer alternatives only when explicitly asked
