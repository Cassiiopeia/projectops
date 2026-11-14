// Architecture rule test: docs/architecture/rules/<id>.rule violations <-> <id>.allow
// Edit rules in the rules folder (this file is a pro-code-consult template — verdict logic only)
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

// Excluded folders (same list as the other stack templates)
const skippedDirectoryNames = {
  '.git', 'build', 'dist', 'node_modules', '.dart_tool', 'Pods', '.gradle',
  'venv', '.venv', '__pycache__', '.next', 'out', 'target', '.idea',
};
const listKeys = {'paths', 'extensions', 'exclude'};
// Rule files themselves are always excluded
const alwaysExcludedPrefix = 'docs/architecture/';

/// Search upward from the current folder for docs/architecture/rules (works from monorepo subfolders)
Directory? findRulesDirectory(Directory start) {
  var directory = start.absolute;
  while (true) {
    final candidate = Directory('${directory.path}/docs/architecture/rules');
    if (candidate.existsSync()) return candidate;
    if (directory.parent.path == directory.path) return null;
    directory = directory.parent;
  }
}

/// key=value (split on the first = only, # comments) > rule
Map<String, dynamic> parseRule(File file) {
  final name = file.uri.pathSegments.last;
  final rule = <String, dynamic>{
    'id': name.substring(0, name.length - '.rule'.length),
    'pattern': '', 'paths': <String>[], 'extensions': <String>[], 'exclude': <String>[],
  };
  for (final raw in file.readAsLinesSync()) {
    final line = raw.trim();
    if (line.isEmpty || line.startsWith('#') || !line.contains('=')) continue;
    final index = line.indexOf('=');
    final key = line.substring(0, index).trim();
    final value = line.substring(index + 1).trim();
    if (listKeys.contains(key)) {
      rule[key] = value.split(',').map((item) => item.trim()).where((item) => item.isNotEmpty).toList();
    } else if (key == 'pattern') {
      rule['pattern'] = value;
    }
  }
  return rule;
}

List<String> readAllowEntries(File file) {
  if (!file.existsSync()) return [];
  return file.readAsLinesSync().map((line) => line.trim())
      .where((line) => line.isNotEmpty && !line.startsWith('#')).toList();
}

Iterable<File> walk(Directory directory) sync* {
  for (final entity in directory.listSync(followLinks: false)) {
    final name = entity.uri.pathSegments.where((segment) => segment.isNotEmpty).last;
    if (entity is Directory) {
      if (!skippedDirectoryNames.contains(name)) yield* walk(entity);
    } else if (entity is File) {
      yield entity;
    }
  }
}

List<String> findViolatingFiles(Directory repositoryRoot, Map<String, dynamic> rule) {
  final pattern = RegExp(rule['pattern'] as String, multiLine: true);
  final paths = (rule['paths'] as List<String>).isEmpty ? [''] : rule['paths'] as List<String>;
  final rootPath = repositoryRoot.absolute.path;
  final violating = <String>{};
  for (final prefix in paths) {
    final basePath = prefix.isEmpty ? rootPath : '$rootPath/$prefix';
    final candidates = FileSystemEntity.isFileSync(basePath)
        ? [File(basePath)]
        : Directory(basePath).existsSync() ? walk(Directory(basePath)).toList() : <File>[];
    for (final file in candidates) {
      final relative = file.absolute.path.substring(rootPath.length + 1).replaceAll('\\', '/');
      if (relative.startsWith(alwaysExcludedPrefix) || (rule['exclude'] as List<String>).any(relative.startsWith)) continue;
      final extensions = rule['extensions'] as List<String>;
      if (extensions.isNotEmpty && !extensions.any(relative.endsWith)) continue;
      if (pattern.hasMatch(utf8.decode(file.readAsBytesSync(), allowMalformed: true))) violating.add(relative);
    }
  }
  return violating.toList()..sort();
}

void main() {
  final rulesDirectory = findRulesDirectory(Directory.current);
  if (rulesDirectory == null) return;
  final repositoryRoot = rulesDirectory.parent.parent.parent;
  final ruleFiles = rulesDirectory.listSync().whereType<File>()
      .where((file) => file.path.endsWith('.rule')).toList()
    ..sort((a, b) => a.path.compareTo(b.path));

  for (final ruleFile in ruleFiles) {
    final rule = parseRule(ruleFile);
    test('architecture rule: ${rule['id']}', () {
      expect(rule['pattern'], isNotEmpty, reason: '${rule['id']}.rule: missing pattern key');
      final violating = findViolatingFiles(repositoryRoot, rule).toSet();
      final allowed = readAllowEntries(File('${rulesDirectory.path}/${rule['id']}.allow')).toSet();

      // New violations (files not in the freeze list) > fix the code
      final newViolations = violating.difference(allowed).toList()..sort();
      expect(newViolations, isEmpty, reason: '[${rule['id']}] new violations: $newViolations');
      // Fixed entries > remove them from the freeze list (keeps the list from loosening)
      final fixedEntries = allowed.difference(violating).toList()..sort();
      expect(fixedEntries, isEmpty, reason: '[${rule['id']}] fixed, so remove from ${rule['id']}.allow: $fixedEntries');
    });
  }
}
