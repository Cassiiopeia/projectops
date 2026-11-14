"""common — shared infrastructure for cassiiopeia skills.

Layer 1 of the 3-layer architecture. Each skill's _cli.py imports this package.
Pure functions and single-responsibility modules only. No skill dependencies.
"""

__version__ = "1.0.0"

# skill_ids that get output paths (used by paths.py and others)
SUPPORTED_SKILL_IDS = [
    "report",
    "review",
    "testcase",
    "issue",
    "github",
    "synology-expose",
]
