// 아키텍처 규칙 테스트: docs/architecture/rules/<id>.rule 위반 <-> <id>.allow 대조
// 규칙은 rules 폴더에서 고친다 (이 파일은 pro-code-consult 템플릿 — 판정 로직만)
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

// 탐색 제외 폴더 (다른 스택 템플릿과 같은 목록)
const skippedDirectoryNames = {
  '.git', 'build', 'dist', 'node_modules', '.dart_tool', 'Pods', '.gradle',
  'venv', '.venv', '__pycache__', '.next', 'out', 'target', '.idea',
};
const listKeys = {'paths', 'extensions', 'exclude'};
// 규칙 파일 자신은 판정 대상에서 늘 제외
const alwaysExcludedPrefix = 'docs/architecture/';

/// 현재 폴더부터 위로 docs/architecture/rules 탐색 (모노레포 서브폴더에서도 동작)
Directory? findRulesDirectory(Directory start) {
  var directory = start.absolute;
  while (true) {
    final candidate = Directory('${directory.path}/docs/architecture/rules');
    if (candidate.existsSync()) return candidate;
    if (directory.parent.path == directory.path) return null;
    directory = directory.parent;
  }
}

/// key=value (첫 = 에서만 자름, # 주석) > 규칙
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
      expect(rule['pattern'], isNotEmpty, reason: '${rule['id']}.rule: pattern 키가 없다');
      final violating = findViolatingFiles(repositoryRoot, rule).toSet();
      final allowed = readAllowEntries(File('${rulesDirectory.path}/${rule['id']}.allow')).toSet();

      // 새 위반 (동결 목록에 없는 파일) > 코드를 고친다
      final newViolations = violating.difference(allowed).toList()..sort();
      expect(newViolations, isEmpty, reason: '[${rule['id']}] 새 위반: $newViolations');
      // 고쳐진 항목 > 동결 목록에서 지운다 (목록이 느슨해지지 않게)
      final fixedEntries = allowed.difference(violating).toList()..sort();
      expect(fixedEntries, isEmpty, reason: '[${rule['id']}] 고쳐졌으니 ${rule['id']}.allow 에서 지운다: $fixedEntries');
    });
  }
}
