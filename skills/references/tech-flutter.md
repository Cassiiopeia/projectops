# Flutter tech guide

## Widget design checklist

- [ ] StatelessWidget vs StatefulWidget is appropriate
- [ ] Widget tree depth (performance)
- [ ] const constructors used (rebuild optimization)
- [ ] BuildContext used correctly
- [ ] Whether Keys are used

## State management

- [ ] Consistent state management pattern (Provider/Riverpod/Bloc)
- [ ] Appropriate state scope (global vs local)
- [ ] dispose handled (memory leaks)
- [ ] Unnecessary rebuilds

## Performance

- [ ] ListView.builder used (large data)
- [ ] Image caching (cached_network_image)
- [ ] Unnecessary setState calls
- [ ] Heavy computation moved to an isolate

## Code style

- [ ] Dart naming rules (lowerCamelCase, UpperCamelCase)
- [ ] File names in snake_case
- [ ] Follows analysis_options.yaml lint rules

## Layout

- [ ] Flexible / Expanded used appropriately
- [ ] Consistent padding / margin
- [ ] SafeArea handled
- [ ] Responsive handling with MediaQuery

## Test patterns

| Test type | Function | Use |
|------------|------|------|
| Unit test | `test()` | Logic verification |
| Widget test | `testWidgets()` | UI rendering |
| Integration test | `integration_test` | Full flow |

## Refactoring points

- **Large widget** → split into private Widget classes (`_ProfileHeader`)
- **Long constructor** → named parameters + copyWith
- **Inline styles** → extract into Theme/Extension

## Project structure (Clean Architecture)

```
lib/
├── core/           # constants, theme, utilities
├── data/           # models, repository implementations, data sources
├── domain/         # entities, repository interfaces, use cases
├── presentation/   # screens, widgets, providers
└── main.dart
```

## Responsive size conversion (Figma → Flutter)

```dart
// Design baseline
const double DESIGN_WIDTH = 375.0;

// Extension pattern
extension ResponsiveSize on num {
  double get w => (SizeConfig.screenWidth / DESIGN_WIDTH) * this;
  double get h => (SizeConfig.screenHeight / DESIGN_HEIGHT) * this;
  double get sp => (SizeConfig.screenWidth / DESIGN_WIDTH) * this;
}
```
