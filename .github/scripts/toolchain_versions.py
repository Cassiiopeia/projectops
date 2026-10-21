#!/usr/bin/env python3
"""
toolchain_versions.py

워크플로우 고정 FLUTTER_VERSION·JAVA_VERSION <-> 레포가 요구하는 버전 대조 (#758). 대조 규칙의 유일한 위치다.

  Flutter 근거 3개: .fvmrc(.fvm/fvm_config.json), .flutter-version, pubspec.yaml environment.flutter 제약
  Java 근거 3개: .java-version, .tool-versions 의 java, Gradle jvmToolchain(N)·JavaLanguageVersion.of(N)
  어긋나면 경고만 (빌드는 계속) — 템플릿 고정값이 낡아도 레포 변수(FLUTTER_VERSION·JAVA_VERSION)로 고칠 수 있게 안내

  - 커맨드: check
  - 출력: ::warning 줄 + 마지막 줄 JSON, GITHUB_STEP_SUMMARY 에 경고 목록
  - 종료 코드: 항상 0 (진단 전용)

사용 예:
  FLUTTER_VERSION=3.38.9 JAVA_VERSION=17 python3 toolchain_versions.py check --app-root .
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

VARIABLES_HINT = ("Set the repository variable {name} (Settings > Secrets and variables > Actions > Variables) "
                  "to override the workflow value, or update {name} in the workflow.")
# 치환 전 자리표시자(__JAVA_VERSION__ 등)는 대조하지 않는다
_PLACEHOLDER_RE = re.compile(r"^__[A-Z_]+__$")
_VERSION_RE = re.compile(r"^\d+(\.\d+){0,2}$")
_PUBSPEC_FLUTTER_RE = re.compile(r"^environment:\s*\n((?:[ \t]+.*\n?)*)", re.M)
_GRADLE_TOOLCHAIN_RES = (
    re.compile(r"jvmToolchain\s*\(\s*(\d+)\s*\)"),
    re.compile(r"JavaLanguageVersion\.of\s*\(\s*(\d+)\s*\)"),
)
GRADLE_FILES = ("android/app/build.gradle", "android/app/build.gradle.kts",
                "android/build.gradle", "android/build.gradle.kts")


def parse_version(text: str) -> tuple[int, int, int] | None:
    """'3.38.9' · '3.38' · 'v3.38.9-0.1.pre' > (3, 38, 9) (pre-release 꼬리는 버림)"""
    core = str(text).strip().lstrip("vV").split("-")[0].split("+")[0]
    if not _VERSION_RE.match(core):
        return None
    parts = [int(p) for p in core.split(".")]
    return tuple(parts + [0] * (3 - len(parts)))  # type: ignore[return-value]


def satisfies(version: tuple[int, int, int], constraint: str) -> bool | None:
    """버전이 pub 제약(>=, >, <=, <, ^, 정확한 값, any)을 만족하는가. 해석 못 하면 None"""
    constraint = constraint.strip().strip("'\"")
    if not constraint or constraint == "any":
        return True
    token_re = r"(>=|<=|>|<|\^|=)?\s*([0-9][0-9A-Za-z.+-]*)"
    # 토큰으로 못 읽는 부분이 남으면 판정하지 않는다 (잘못 경고하느니 침묵)
    if re.sub(token_re, "", constraint).strip():
        return None
    for operator, raw in re.findall(token_re, constraint):
        bound = parse_version(raw)
        if bound is None:
            return None
        if operator == "^":
            upper = (bound[0] + 1, 0, 0) if bound[0] > 0 else (0, bound[1] + 1, 0)
            if not (bound <= version < upper):
                return False
        elif operator == ">=" and not version >= bound:
            return False
        elif operator == ">" and not version > bound:
            return False
        elif operator == "<=" and not version <= bound:
            return False
        elif operator == "<" and not version < bound:
            return False
        elif operator in ("", "=") and version != bound:
            return False
    return True


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def flutter_requirements(app_root: Path) -> list[dict]:
    """레포의 Flutter 요구 > [{source, kind: exact|constraint, value}]"""
    found = []
    for name, keys in ((".fvmrc", ("flutter", "flutterSdkVersion")),
                       (".fvm/fvm_config.json", ("flutterSdkVersion", "flutter"))):
        text = _read(app_root / name)
        if not text:
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        value = next((str(data[k]) for k in keys if isinstance(data, dict) and data.get(k)), "")
        # 채널 이름(stable 등)은 버전이 아니라 대조하지 않는다
        if parse_version(value):
            found.append({"source": name, "kind": "exact", "value": value})
    pinned = _read(app_root / ".flutter-version").strip()
    if parse_version(pinned):
        found.append({"source": ".flutter-version", "kind": "exact", "value": pinned})
    match = _PUBSPEC_FLUTTER_RE.search(_read(app_root / "pubspec.yaml"))
    if match:
        line = re.search(r"^[ \t]+flutter:\s*(.+?)\s*(#.*)?$", match.group(1), re.M)
        if line:
            found.append({"source": "pubspec.yaml environment.flutter", "kind": "constraint",
                          "value": line.group(1).strip().strip("'\"")})
    return found


def java_requirements(app_root: Path) -> list[dict]:
    """레포의 Java 요구 > [{source, value: 주 버전}]"""
    found = []
    major = re.match(r"^\s*(?:1\.)?(\d+)", _read(app_root / ".java-version"))
    if major:
        found.append({"source": ".java-version", "value": major.group(1)})
    tool = re.search(r"^java\s+\S*?(\d+)(?:[.\s]|$)", _read(app_root / ".tool-versions"), re.M)
    if tool:
        found.append({"source": ".tool-versions", "value": tool.group(1)})
    for name in GRADLE_FILES:
        text = _read(app_root / name)
        for pattern in _GRADLE_TOOLCHAIN_RES:
            hit = pattern.search(text)
            if hit:
                found.append({"source": f"{name} toolchain", "value": hit.group(1)})
                break
    return found


def check(app_root: Path, flutter_version: str, java_version: str) -> dict:
    """대조 > {ok, findings: [{tool, source, message}], checked: [...]}"""
    findings, checked = [], []
    flutter = parse_version(flutter_version) if flutter_version and not _PLACEHOLDER_RE.match(flutter_version) else None
    if flutter:
        for req in flutter_requirements(app_root):
            checked.append(req["source"])
            if req["kind"] == "exact":
                matched = parse_version(req["value"]) == flutter
                need = req["value"]
            else:
                matched = satisfies(flutter, req["value"])
                need = req["value"]
                if matched is None:
                    continue
            if not matched:
                findings.append({"tool": "flutter", "source": req["source"], "message": (
                    f"{req['source']} asks for Flutter {need} but the workflow uses FLUTTER_VERSION "
                    f"{flutter_version}. " + VARIABLES_HINT.format(name="FLUTTER_VERSION"))})
    java = re.match(r"^\s*(?:1\.)?(\d+)", java_version or "")
    if java and not _PLACEHOLDER_RE.match(java_version):
        for req in java_requirements(app_root):
            checked.append(req["source"])
            if req["value"] != java.group(1):
                findings.append({"tool": "java", "source": req["source"], "message": (
                    f"{req['source']} asks for Java {req['value']} but the workflow uses JAVA_VERSION "
                    f"{java_version}. " + VARIABLES_HINT.format(name="JAVA_VERSION"))})
    return {"ok": True, "flutter_version": flutter_version, "java_version": java_version,
            "checked": checked, "findings": findings,
            "summary": (f"{len(findings)} toolchain version mismatch(es)" if findings
                        else "Toolchain versions match the repository")}


def command_check(args: argparse.Namespace) -> int:
    flutter_version = (args.flutter_version if args.flutter_version is not None
                       else os.environ.get("FLUTTER_VERSION", "")).strip()
    java_version = (args.java_version if args.java_version is not None
                    else os.environ.get("JAVA_VERSION", "")).strip()
    result = check(Path(args.app_root), flutter_version, java_version)
    for finding in result["findings"]:
        print(f"::warning title=Toolchain version mismatch ({finding['tool']})::{finding['message']}")
    if not result["findings"]:
        print(f"{result['summary']} (Flutter {flutter_version or '-'}, Java {java_version or '-'}; "
              f"checked: {', '.join(result['checked']) or 'nothing to compare'})")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path and result["findings"]:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("### Toolchain version mismatch\n\n")
            handle.write("".join(f"- {f['message']}\n" for f in result["findings"]))
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare the workflow's pinned Flutter/Java versions with the repository")
    sub = parser.add_subparsers(dest="command", required=True)
    check_parser = sub.add_parser("check", help="warn when the repository asks for other Flutter/Java versions")
    check_parser.add_argument("--app-root", default=".", help="Flutter project root (APP_ROOT)")
    check_parser.add_argument("--flutter-version", default=None, help="overrides the FLUTTER_VERSION env")
    check_parser.add_argument("--java-version", default=None, help="overrides the JAVA_VERSION env")
    check_parser.set_defaults(handler=command_check)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
