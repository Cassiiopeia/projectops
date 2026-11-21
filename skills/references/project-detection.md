# Automatic project type detection

Determine the type from which files exist at the project root.

## Detection rules

<!-- generated: project-types:detection -->
| Type | Required files | Secondary checks |
|------|------|------|
| **Flutter** (`flutter`) | `pubspec.yaml` | `lib/` directory |
| **Spring Boot** (`spring`) | `build.gradle` or `build.gradle.kts` or `pom.xml` | `src/main/java/`, Spring dependencies |
| **Python** (`python`) | `pyproject.toml` or `setup.py` or `requirements.txt` | `manage.py` (Django), `main.py` (FastAPI) |
| **React / Next.js** (`react`) | `package.json` + `react` or `next` dependency, no `react-native` or `@react-native/*` | `src/` or `app/`, `tsconfig.json`, `next.config.js` |
| **React Native CLI** (`react-native`) | `package.json` + `react-native` or `@react-native/*` dependency, no `expo` | `android/`, `ios/` directories |
| **React Native (Expo)** (`react-native-expo`) | `package.json` + `expo` and `react-native` or `@react-native/*` dependency | `expo` key in `app.json`; `android/` and `ios/` may be absent |
| **Node.js** (`node`) | `package.json` (only when no other type matches) | `express`, `fastify`, and so on |
| **Basic** (`basic`) | Matches no other type | Only `version.yml` exists |
<!-- /generated -->

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
