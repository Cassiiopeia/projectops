#!/usr/bin/env python3
"""Builds the text the QA issue creation bot posts (#787) — stdlib only.

Assembling text inside the workflow JS is untestable and bloats the YAML. JS decides only numbers and titles;
this module returns title, body, comment and error text in the right language. The text itself lives in i18n/*.json (qa_bot.*).

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
    # Removing keyword tags is the JS side's job. Here only remaining leading [tags] are stripped once more for the "test target" text.
    target = re.sub(r"^\[.*?\]\s*", "", title)
    body = t("qa_bot.body", lang,
             issue_number=original,
             pr_issue_line=f"- PR: #{pr}" if pr else "",
             pr_info=f"- #{pr}" if pr else t("qa_bot.pr_placeholder", lang),
             target=target,
             requester=requester)
    return {"title": t("qa_bot.title", lang, title=title), "body": body}


def build_comment(lang: str | None, qa_number: int, original: int | None) -> str:
    """Comment on the original issue/PR. With original (started from a PR), issue info is included."""
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
    # Windows console default encodings (cp1252, etc.) cannot write emoji or Korean and crash — always output UTF-8
    sys.stdout.buffer.write((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
