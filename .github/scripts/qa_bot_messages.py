#!/usr/bin/env python3
"""QA 이슈 생성 봇이 게시하는 문구를 만든다 (#787) — stdlib 전용.

문구 조립을 워크플로우 JS 안에 두면 테스트할 수 없고 YAML 이 두꺼워진다. JS 는 숫자와 제목만 정하고,
이 모듈이 언어에 맞는 제목·본문·댓글·오류 문구를 돌려준다. 문구 자체는 i18n/*.json (qa_bot.*) 이다.

  qa_bot_messages.py issue   --title T --original N [--pr N] --requester U [--lang L]   → {"title","body"}
  qa_bot_messages.py comment --qa N [--original N] [--lang L]                           → {"comment"}
  qa_bot_messages.py error   --message M [--lang L]                                     → {"error"}
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from i18n.messages import resolve_language, t


def build_issue(lang: str | None, title: str, original: int, pr: int | None, requester: str) -> dict:
    lang = lang or resolve_language()
    # 키워드 태그 제거는 JS 쪽 책임이다. 여기서는 남은 앞쪽 [태그]만 한 번 더 걷어 "시험 대상" 문구에 쓴다.
    target = re.sub(r"^\[.*?\]\s*", "", title)
    body = t("qa_bot.body", lang,
             issue_number=original,
             pr_issue_line=f"- PR: #{pr}" if pr else "",
             pr_info=f"- #{pr}" if pr else t("qa_bot.pr_placeholder", lang),
             target=target,
             requester=requester)
    return {"title": t("qa_bot.title", lang, title=title), "body": body}


def build_comment(lang: str | None, qa_number: int, original: int | None) -> str:
    """원본 이슈/PR 에 다는 댓글. original 이 있으면(PR 에서 시작) 이슈 정보를 함께 적는다."""
    lang = lang or resolve_language()
    lines = [t("qa_bot.comment.created", lang), "", t("qa_bot.comment.qa_heading", lang), f"- #{qa_number}", ""]
    if original:
        lines += [t("qa_bot.comment.issue_heading", lang), f"- #{original}", ""]
    lines.append(t("qa_bot.comment.done", lang))
    return "\n".join(lines)


def build_error(lang: str | None, message: str) -> str:
    lang = lang or resolve_language()
    return f"{t('qa_bot.error', lang)}\n\n```\n{message}\n```"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("issue")
    i.add_argument("--title", required=True)
    i.add_argument("--original", type=int, required=True)
    i.add_argument("--pr", type=int, default=None)
    i.add_argument("--requester", required=True)
    c = sub.add_parser("comment")
    c.add_argument("--qa", type=int, required=True)
    c.add_argument("--original", type=int, default=None)
    e = sub.add_parser("error")
    e.add_argument("--message", required=True)
    for p in (i, c, e):
        p.add_argument("--lang", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "issue":
        out = build_issue(a.lang, a.title, a.original, a.pr, a.requester)
    elif a.cmd == "comment":
        out = {"comment": build_comment(a.lang, a.qa, a.original)}
    else:
        out = {"error": build_error(a.lang, a.message)}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
