"""Strings that are never translated — old consumers already running in user repos read them with regexes (#787).

These values are not put in the message catalogs (*.json). Code takes them from here.
A test (test_i18n_messages.py) checks these strings are not mixed into catalog values.

Consumers: app build trigger, test APK, TestFlight workflows (docs/BRANCH-CONVENTION.md)
"""

# Branch code block heading in the issue helper comment: /### 브랜치\s*```\s*([\s\S]*?)\s*```/
BRANCH_HEADING = "### 브랜치"
# Comment signature (configurable via guide_signature, but the default is the contract)
SIGNATURE = "Guide by ProjectOps"
# Old signature: old consumers look for it. Always kept as an invisible comment (bytes unchanged, including the text in parentheses)
LEGACY_SIGNATURE = "Guide by SUH-LAB"
LEGACY_COMMENT = f"<!-- {LEGACY_SIGNATURE} (구버전 워크플로우 호환용 표식) -->"
# Release-notes body marker: the release workflow uses this text to tell whether a summary exists
CODERABBIT_MARKER = "Summary by CodeRabbit"

ALL = (BRANCH_HEADING, SIGNATURE, LEGACY_SIGNATURE, CODERABBIT_MARKER)
