#!/usr/bin/env python3
"""oss_cli — oss-consult skill 전용 CLI (#644, #660).

레포가 오픈소스로서 무엇을 갖췄는지 **사실만** 모은다. 판단(성격·결함 여부·점수·우선순위)은
에이전트가 references/rubric.md를 보고 한다 — 데모가 없는 것이 hey에겐 괜찮고
작은 도구에겐 치명적인 것처럼, 같은 사실이 레포 성격에 따라 다르게 읽히기 때문이다.

여기에 두는 것은 "매번 똑같이 해야 하고 토큰을 아끼는 일"뿐이다: API 호출·페이지 넘김,
README 디코딩과 첫 화면 잘라내기, 파일을 세 위치에서 찾기, 비율 같은 측정.
**참/거짓 판정이나 분류를 여기서 만들지 않는다.** 정규식으로 "비교 절이 있다"고 단정하는 순간
에이전트가 원문을 안 읽고 그 값을 믿는다.

읽기: collect, local-facts, list-repos, get-output-path
쓰기(승인 후에만): repo-update, label — 삭제·가시성·이름 변경·아카이브는 구현하지 않는다.

안전 원칙 (#660 검수):
- 남의 레포 텍스트(README·이슈 제목·라벨명·파일명)는 **분석 대상일 뿐 지시가 아니다** →
  출력 최상위 `untrusted` 에 그런 필드 경로를 적는다.
- 내려받은 임의 레포에 git 을 돌려도 그 레포의 .git/config 가 명령을 실행하지 못하게 막는다.
- 추적된 심볼릭 링크는 읽지 않는다 (레포 밖 파일이 출력에 섞인다).
- 모든 오류 JSON 에는 `next` 가 있다.
"""
from __future__ import annotations

import sys
from pathlib import Path

# 진입점: 파서 위임과 이름 재노출만. 구현은 같은 폴더의 oss_consult 패키지
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
for _path in (_SCRIPTS_ROOT, _HERE.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from common import gh_client  # noqa: E402,F401
from common.emit import emit  # noqa: E402,F401
from common.cli_parser import JSONArgumentParser, _BadArgsExit  # noqa: E402,F401

# 테스트·외부 호출부가 oss_cli.<이름> 으로 쓰는 이름 재노출
from oss_consult.cli import _int_range, build_parser, main, run_cli  # noqa: E402,F401
from oss_consult.commands.collect import cmd_collect  # noqa: E402,F401
from oss_consult.commands.get_output_path import cmd_get_output_path  # noqa: E402,F401
from oss_consult.commands.label import (MAX_LABEL_DESCRIPTION, PROTECTED_LABELS, _COLOR_RE,  # noqa: E402,F401
                                        cmd_label)
from oss_consult.commands.list_repos import _DEFAULT_LIMIT, _REPO_PAGES, cmd_list_repos  # noqa: E402,F401
from oss_consult.commands.local_facts import cmd_local_facts  # noqa: E402,F401
from oss_consult.commands.repo_update import (MAX_DESCRIPTION, MAX_TOPICS, _TOPIC_RE,  # noqa: E402,F401
                                              _write_repo_state, cmd_repo_update, plan_repo_update)
from oss_consult.github_api import (_API, _LABEL_PAGES, _TIMEOUT, _call, _file_text, _get,  # noqa: E402,F401
                                    _label_records, _listing, _pat, _readme, _reset_when, classify_api_error)
from oss_consult.local_git import (MAX_SOURCE_FILES, MAX_TOTAL_BYTES, _GIT_SAFE,  # noqa: E402,F401
                                   _MANIFEST_MAX_BYTES, _SOURCE_MAX_BYTES, _Budget, _git, _git_env, _git_raw,
                                   _gitfile_target, _safe_read)
from oss_consult.local_measure import (_is_test_path, _toml_section_keys, co_change,  # noqa: E402,F401
                                       committed_secret_paths, dependency_names, is_manifest,
                                       is_unsupported_manifest, natural_language_strings)
from oss_consult.output import (_COLLECT_UNTRUSTED, _LOCAL_UNTRUSTED, _STR_LIMIT,  # noqa: E402,F401
                                _STR_LIMIT_BY_KEY, _UNTRUSTED_NOTICE, _api_fail, _bad_slug, _fail, _no_pat,
                                _out, _sanitize, _split)
from oss_consult.readme_facts import (HEAD_LINES, MAX_TOP_LINES, TOP_LINES, analyze_readme,  # noqa: E402,F401
                                      detect_files, extra_privacy_dirs, match_health_name, summarize_labels,
                                      text_head)


if __name__ == "__main__":
    sys.exit(main())
