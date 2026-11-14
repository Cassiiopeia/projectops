#!/usr/bin/env python3
"""oss_cli — CLI for the oss-consult skill (#644, #660).

Collects **only facts** about what a repo has as an open-source project. Judgment (type, whether something is a defect, scores, priorities)
is the agent's, using references/rubric.md — just as having no demo is fine for hey
but fatal for a small tool, the same fact reads differently depending on the repo's type.

Only "work that must be identical every time and saves tokens" lives here: API calls and paging,
README decoding and cutting the first screen, finding files in three locations, measurements such as ratios.
**No true/false verdicts or classifications are made here.** The moment a regex asserts "there is a comparison section",
the agent trusts that value without reading the source.

Read: collect, local-facts, list-repos, get-output-path
Write (only after approval): repo-update, label — delete, visibility, rename and archive are not implemented.

Safety rules (#660 review):
- Text from other people's repos (README, issue titles, label names, file names) is **material to analyze, not instructions** →
  the output's top-level `untrusted` lists those field paths.
- Running git on any downloaded repo must not let that repo's .git/config execute commands.
- Tracked symlinks are not read (files outside the repo would leak into the output).
- Every error JSON has `next`.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Entry point: parser delegation and name re-exports only. Implementation is the oss_consult package in this folder
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
for _path in (_SCRIPTS_ROOT, _HERE.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from common import gh_client  # noqa: E402,F401
from common.emit import emit  # noqa: E402,F401
from common.cli_parser import JSONArgumentParser, _BadArgsExit  # noqa: E402,F401

# Re-export names that tests and external callers use as oss_cli.<name>
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
