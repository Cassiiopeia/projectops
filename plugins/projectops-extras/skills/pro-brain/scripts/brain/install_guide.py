"""Guided GBrain install and init: detect gbrain, ask one question, give exact commands, prerequisites and the check after
Read-only: it never runs init or serve, because those take connection strings and keys the user types in a terminal.
Commands follow `gbrain init --help` and `gbrain serve --help` of gbrain 0.60.
"""
from __future__ import annotations

from . import brain_usage

INSTALL_CHOICES = ("local", "postgres", "supabase", "thin-client", "team-server")
VERIFY_COMMANDS = ["gbrain engine status --json", "gbrain doctor --fast --json"]
# The secret-bearing commands are typed by the user (Claude Code `!` prefix or a separate terminal), never through chat
TYPE_IT_YOURSELF = "type this yourself in a terminal (it carries a password or key): never paste it into the chat"

GUIDES = {
    "local": {
        "label": "Only me, on this computer (PGLite, no server, no keys)",
        "requires": [],
        "commands": ["gbrain init --pglite"],
        "then": "brain_cli.py connect (adds this repo's knowledge folder as one source)",
    },
    "postgres": {
        "label": "Only me, on a Postgres I already run",
        "requires": ["the database and the role must exist first: gbrain applies its schema migrations but creates "
                     "neither (ask the database owner, or create them with your usual admin tool)"],
        "commands": ['gbrain init --url "postgresql://<role>:<password>@<host>:<port>/<database>"'],
        "secret_note": TYPE_IT_YOURSELF,
        "then": "brain_cli.py connect",
    },
    "supabase": {
        "label": "Only me, on Supabase (large brains, 1000+ files)",
        "requires": ["a Supabase project (gbrain asks for its connection details interactively)"],
        "commands": ["gbrain init --supabase"],
        "secret_note": TYPE_IT_YOURSELF,
        "then": "brain_cli.py connect",
    },
    "thin-client": {
        "label": "My own brain runs on another machine; this one only connects to it",
        "requires": ["the brain host's MCP URL and an OAuth client id and secret issued on that host"],
        "commands": ["gbrain init --mcp-only --issuer-url https://<host> --mcp-url https://<host>/mcp "
                     "--oauth-client-id <id> --oauth-client-secret <secret>"],
        "secret_note": TYPE_IT_YOURSELF,
        "then": "brain_cli.py connect --remote (prints the commands to run on the brain host)",
    },
    "team-server": {
        "label": "A brain my whole team reads (I run the server)",
        "requires": ["a brain on the server (one of the four above, Postgres recommended)",
                     "an HTTPS address teammates can reach (reverse proxy or tunnel in front of the port)"],
        "commands": ["gbrain serve --http --port 3131 --bind 0.0.0.0 --public-url https://<host>",
                     "gbrain auth create <member> --scopes read   # one per member; a brain serving several people "
                     "also needs --member <id> (see gbrain auth --help)",
                     "brain_cli.py setup --apply --yes --team-brain-name gbrain-<project> "
                     "--team-brain-url https://<host>/mcp --team-brain-contact <who issues tokens>"],
        "secret_note": "hand each member their token privately; they store it with cred set --prompt (never chat)",
        "then": "each member: store the token once, then brain_cli.py connect --team (references/how-it-works.md)",
    },
}


def recommend_choice(detected: dict) -> str:
    if detected.get("kind") == "remote":
        return "thin-client"
    return "local"


def guide(choice: str | None) -> dict:
    """Facts + question (no choice) or the full guide for one choice"""
    detected = brain_usage.detect_gbrain()
    version = None
    if detected["installed"]:
        _, version_text = brain_usage.run_gbrain("--version")
        version = version_text.strip().splitlines()[0] if version_text.strip() else None
    facts = {"gbrain": {"installed": detected["installed"], "version": version, "kind": detected["kind"],
                        "brain_ready": detected["brain_ready"], "engine": detected.get("engine")},
             "install_url": brain_usage.GBRAIN_INSTALL_URL}
    if not choice:
        if detected["brain_ready"]:
            return {**facts, "code": "brain_ready",
                    "summary": f"gbrain is set up here ({detected['kind']} brain): nothing to install",
                    "next": "brain_cli.py connect (personal) or connect --team (team brain)"}
        return {**facts, "code": "question", "recommended": recommend_choice(detected),
                "question": "Where should your brain live?",
                "choices": [{"id": key, "label": GUIDES[key]["label"]} for key in INSTALL_CHOICES],
                "summary": ("gbrain is not installed" if not detected["installed"] else "gbrain is installed but has no brain yet"),
                "next": "ask the one question (recommended first), then install --choice <id>"}
    selected = GUIDES[choice]
    steps = [] if detected["installed"] else [f"install gbrain first: {brain_usage.GBRAIN_INSTALL_URL} (README, Install)"]
    return {**facts, "code": "guide", "choice": choice, "label": selected["label"], "requires": selected["requires"],
            "install_steps": steps, "commands": selected["commands"], "secret_note": selected.get("secret_note"),
            "verify": VERIFY_COMMANDS, "then": selected["then"],
            "summary": f"{choice}: {len(selected['requires'])} prerequisite(s), {len(selected['commands'])} command(s)",
            "next": "show the commands; the user runs them (secret-bearing ones in a terminal); then run install again to verify"}
