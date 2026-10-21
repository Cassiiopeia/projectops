# Automatic project type detection

Determine the type from which files exist at the project root.

## Detection rules

| Type | Required files | Secondary checks |
|------|----------|----------|
| **Spring Boot** | `pom.xml` or `build.gradle` / `build.gradle.kts` | `src/main/java/`, Spring dependencies |
| **React** | `package.json` + `react` dependency | `src/` or `app/`, `tsconfig.json` |
| **React Native** | `package.json` + `react-native` dependency | `android/`, `ios/` directories |
| **React Native Expo** | `package.json` + `expo` dependency | `expo` key in `app.json`; `android/` and `ios/` may be absent |
| **Flutter** | `pubspec.yaml` | `lib/` directory |
| **Next.js** | `package.json` + `next` dependency | `next.config.js` |
| **Node.js** | `package.json` (no framework) | `express`, `fastify`, and so on |
| **Python** | `pyproject.toml` or `requirements.txt` | `manage.py` (Django), `main.py` (FastAPI) |
| **basic** | Matches none of the types above | Only `version.yml` exists |

## Detection order

> **React Native vs Expo**: if there is an `expo` dependency, it is Expo; if there is only `react-native`, it is React Native CLI

1. Check root files → determine the type
2. Check framework versions in dependency and config files
3. Learn the architecture pattern from the directory structure

## When detection fails

If nothing matches, treat it as the `basic` type and apply the general rules.

## Output after detection

```
**Detected project type**: [type name]
**Main tech stack**: [framework version, language version, and so on]
```
