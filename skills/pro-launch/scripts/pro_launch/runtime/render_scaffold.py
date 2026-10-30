"""`render scaffold` — Flutter 임시 렌더 폴더 생성 (폰트 로더 · 골든 테스트 뼈대 · shots/) (#948)."""
from __future__ import annotations

import json
import re
import shlex
import time
from pathlib import Path

from pro_launch.runtime.app_identity import find_flutter_root
from pro_launch.runtime.context import state_home


#
# 매 실행마다 하네스를 손으로 다시 짜느라 도구 호출 80-150회가 들었다 (#948).
# 폴더 하나를 통째로 이 명령이 만들고, 이미 있으면 거절한다 — 남의 작업을 덮지 않는다.
# 만든 목록은 manifest(레포 밖 상태 폴더)에 남겨 run 의 청소·재시도 판단에 쓴다.
SCAFFOLD_FOLDER = "test/_launch_render"
SCAFFOLD_MANIFEST = "render-scaffold.json"
# 렌더 레시피 문서 (unsupported_stack 일 때 next 로 안내)
RENDER_RECIPE = "references/render.md"
# Flutter 외 스택 마커: 파일명 > 스택 이름
_OTHER_STACK_MARKERS = (("package.json", "react/node"), ("build.gradle", "spring"),
                        ("build.gradle.kts", "spring"), ("pom.xml", "maven"),
                        ("pyproject.toml", "python"), ("requirements.txt", "python"))


def scaffold_manifest_path(root: Path) -> Path:
    return state_home(root) / SCAFFOLD_MANIFEST


def read_scaffold_manifest(root: Path) -> dict | None:
    f = scaffold_manifest_path(root)
    if not f.is_file():
        return None
    try:
        saved = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return saved if saved.get("root") == str(root) else None


def settle_scaffold_after_run(root: Path) -> dict | None:
    """run 청소 뒤 scaffold 상태: 폴더가 사라졌으면 manifest 삭제, 남았으면 경고용 정보"""
    saved = read_scaffold_manifest(root)
    if saved is None:
        return None
    folder = root / saved["folder"]
    if not folder.exists():
        scaffold_manifest_path(root).unlink(missing_ok=True)
        return {"scaffold": "cleaned"}
    return {"scaffold": "still_present",
            "scaffold_warning": f"Scaffold folder is still there: {saved['folder']} — add --cleanup {saved['folder']}"}


def _project_paths_flutter(root: Path) -> str | None:
    """version.yml project_paths.flutter 값 (모노레포 하위 폴더). 없으면 None"""
    f = root / "version.yml"
    if not f.is_file():
        return None
    in_paths = False
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        if re.match(r"^project_paths:", line):
            in_paths = True
            continue
        if in_paths:
            if line and not line[:1].isspace():
                break
            m = re.match(r"^\s+flutter:\s*[\"']?([^\"'#\s]+)", line)
            if m:
                return m.group(1)
    return None


def _is_flutter_app(folder: Path) -> bool:
    pub = folder / "pubspec.yaml"
    try:
        return pub.is_file() and "flutter:" in pub.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def _resolve_flutter_app(root: Path, app_arg: str | None) -> Path | None:
    """Flutter 앱 폴더 찾기: --app > version.yml project_paths > pubspec.yaml 탐색"""
    for candidate in (app_arg, _project_paths_flutter(root)):
        if candidate and _is_flutter_app(root / candidate):
            return (root / candidate).resolve()
    if app_arg:
        return None   # 명시한 폴더가 Flutter 앱이 아니면 엉뚱한 앱을 고르지 않는다
    found = find_flutter_root(root)
    return found.resolve() if found else None


def _other_stacks(root: Path) -> list[str]:
    kinds = []
    for marker, kind in _OTHER_STACK_MARKERS:
        if any("node_modules" not in f.parts for f in list(root.rglob(marker))[:10]) and kind not in kinds:
            kinds.append(kind)
    return kinds


def _package_name(app: Path) -> str:
    m = re.search(r"^name:\s*([\w]+)", (app / "pubspec.yaml").read_text(encoding="utf-8", errors="ignore"), re.M)
    return m.group(1) if m else "your_app"


# 폰트 로더: 앱 FontManifest(pubspec fonts·MaterialIcons·패키지 아이콘) + SDK Roboto·MaterialIcons
# 아이콘이 □ 로 나오던 함정(render.md)을 뼈대가 미리 막는다 (#948)
_FONT_CONFIG_DART = """\
// Created by `launch_cli.py render scaffold` (#948) — deleted with this folder after render run.
// Applies only to tests in this folder: loads real fonts so text and icons are not drawn as boxes.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();
  final loaded = await _loadManifestFonts();
  await _loadSdkFonts(loaded);
  await testMain();
}

/// Fonts the app declares (pubspec `fonts:`, MaterialIcons with uses-material-design, package icon fonts).
Future<Set<String>> _loadManifestFonts() async {
  final loaded = <String>{};
  try {
    final manifest = json.decode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>;
    for (final entry in manifest.cast<Map<String, dynamic>>()) {
      final family = entry['family'] as String;
      final assets = (entry['fonts'] as List<dynamic>).map((f) => (f as Map<String, dynamic>)['asset'] as String);
      // Package fonts are looked up as 'packages/<pkg>/<family>'; also register the bare name.
      final names = {family, family.replaceFirst(RegExp(r'^packages/[^/]+/'), '')};
      for (final name in names) {
        final loader = FontLoader(name);
        for (final asset in assets) {
          loader.addFont(rootBundle.load(asset));
        }
        await loader.load();
        loaded.add(name);
      }
    }
  } catch (error) {
    // ignore: avoid_print
    print('[launch render] FontManifest.json not loaded: $error');
  }
  return loaded;
}

/// SDK copies of Roboto (default Material text on the test platform) and MaterialIcons.
Future<void> _loadSdkFonts(Set<String> loaded) async {
  final flutterRoot = Platform.environment['FLUTTER_ROOT'];
  if (flutterRoot == null) return;
  final dir = Directory('$flutterRoot/bin/cache/artifacts/material_fonts');
  if (!dir.existsSync()) return;
  final files = dir.listSync().whereType<File>().toList();
  Future<void> load(String family, bool Function(String name) pick) async {
    if (loaded.contains(family)) return;
    final picked = files.where((f) => pick(f.uri.pathSegments.last)).toList();
    if (picked.isEmpty) return;
    final loader = FontLoader(family);
    for (final file in picked) {
      loader.addFont(file.readAsBytes().then((bytes) => ByteData.view(bytes.buffer)));
    }
    await loader.load();
  }

  await load('Roboto', (name) => name.startsWith('Roboto-') && name.endsWith('.ttf'));
  await load('MaterialIcons', (name) => name.startsWith('MaterialIcons') && name.endsWith('.otf'));
}
"""

# 골든 뼈대: 상태 1개 예시 (아이콘 + 텍스트). agent 가 실제 화면 위젯으로 바꾼다
_RENDER_TEST_DART = """\
// Created by `launch_cli.py render scaffold` (#948) — deleted with this folder after render run.
// Replace the example with the real screen widget and fake data. One testWidgets per state.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart'; // MethodChannel · SystemChrome — for stubbing plugin channels
import 'package:flutter_test/flutter_test.dart';
// import 'package:{package}/...'; // the real screen widget and its models

void main() {
  Widget wrap(Widget child) => MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: ThemeData(), // use the repo's theme
        home: Scaffold(body: child),
      );

  testWidgets('example', (tester) async {
    // Phone-sized viewport (390x844 logical points at 3x)
    tester.view.physicalSize = const Size(1170, 2532);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(wrap(const Center(
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(Icons.favorite, color: Colors.red),
        SizedBox(width: 8),
        Text('Replace with the real screen'),
      ]),
    )));
    await tester.pumpAndSettle();
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('shots/example.png'));
  });
}
"""


def _rel(root: Path, target: Path) -> str:
    return target.resolve().relative_to(root.resolve()).as_posix()


def render_scaffold(root: Path, app_arg: str | None, take_baseline) -> dict:
    """Flutter 앱 찾기 > 폴더 존재 시 거절 > 기준선 확보 > 파일 생성 > manifest 기록"""
    app = _resolve_flutter_app(root, app_arg)
    if app is None:
        others = _other_stacks(root)
        if app_arg or not others:
            return {"ok": False, "code": "flutter_app_not_found",
                    "error": f"No Flutter app (pubspec.yaml with flutter:) found{' at --app ' + app_arg if app_arg else ''}",
                    "next": "Pass --app <folder with pubspec.yaml> (relative to --root)"}
        return {"ok": False, "code": "unsupported_stack", "detected": others,
                "error": "render scaffold supports Flutter only",
                "next": f"Write the temporary render code by hand following the stack's recipe in {RENDER_RECIPE}, then render run"}

    folder = app / SCAFFOLD_FOLDER
    folder_rel = _rel(root, folder)
    if folder.exists():
        saved = read_scaffold_manifest(root)
        is_ours = bool(saved and saved.get("folder") == folder_rel)
        return {"ok": False, "code": "scaffold_exists", "folder": folder_rel,
                "created_by_scaffold": is_ours,
                "error": f"{folder_rel} already exists — not overwritten",
                "next": (f"A previous scaffold left it: remove it with render run --cmd true --cleanup {folder_rel}, then scaffold again"
                         if is_ours else "Someone else's files may be there. Do not delete them; ask the user")}

    # 기준선은 임시 파일을 만들기 **전**에 (render.md ① — 빠뜨린 청소가 흔적으로 잡히게)
    baseline = take_baseline()

    shots = folder / "shots"
    config_file = folder / "flutter_test_config.dart"
    test_file = folder / "render_test.dart"
    shots.mkdir(parents=True)
    config_file.write_text(_FONT_CONFIG_DART, encoding="utf-8")
    test_file.write_text(_RENDER_TEST_DART.replace("{package}", _package_name(app)), encoding="utf-8")
    created = [folder_rel, _rel(root, shots), _rel(root, config_file), _rel(root, test_file)]

    manifest = scaffold_manifest_path(root)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"root": str(root), "app": _rel(root, app) or ".", "folder": folder_rel,
                                    "created": created, "at": time.strftime("%Y-%m-%d %H:%M:%S")},
                                   ensure_ascii=False), encoding="utf-8")

    app_rel = _rel(root, app)
    shots_glob = f"{folder_rel}/shots/*.png"
    run_cmd = ["render", "run", "--root", str(root)]
    if app_rel:
        run_cmd += ["--cwd", app_rel]
    run_cmd += ["--cmd", f"flutter test {SCAFFOLD_FOLDER} --update-goldens",
                "--collect", shots_glob, "--cleanup", folder_rel]
    return {"ok": True, "app": app_rel or ".", "folder": folder_rel, "created": created,
            "manifest": str(manifest), "baseline": baseline,
            "summary": f"Created {folder_rel} (font loader incl. MaterialIcons, golden skeleton, shots/)",
            "next": "Edit " + _rel(root, test_file) + " to render the real screen, then: "
                    "{PYTHON} {SCRIPTS}/launch_cli.py " + " ".join(shlex.quote(a) for a in run_cmd)}
