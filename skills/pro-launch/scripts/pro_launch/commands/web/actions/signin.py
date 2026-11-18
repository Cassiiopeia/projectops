"""`web signin` — pick the sign-in engine and, for Ego Lite, hand the stored sign-in information to the agent (#1231).

engine ego:    starts no browser. Returns provider, account, password, second-factor kind and sign-in policy so the agent signs in
               through ego-browser by reading each page (no per-site script). The password is in this result on purpose (owner's choice).
engine legacy: starts nothing either; points to the current flow (web open, web type --cred, web login).
`web login` is not touched: it still needs an attached page and still never prints values.
Both successes use code `ok` (the attempt tracker counts any other code as a failure); the engine is told by the `engine` field.
"""
from __future__ import annotations

import credentials

from pro_launch.registry import Action
from pro_launch.runtime import browser_profiles, ego_engine
from pro_launch.runtime.context import project_root
from pro_launch.runtime.creds import load_cred
from pro_launch.runtime.output import out

ENGINE_CHOICES = ("auto", "ego", "legacy")
# Section of the sign-in guide the agent follows after a hand-over
EGO_GUIDE_POINTER = "references/web-sign-in.md, section 'Ego Lite engine'"


def _has_signed_in_current_profile(root, provider: str | None) -> bool:
    """A current-engine profile already marked as signed in for this provider (web profile mark --kind login --name <provider>)."""
    if not provider:
        return False
    return browser_profiles.profile_with_marks(root, [f"login:{provider}"]) is not None


def execute(args) -> int:
    credential, failure = load_cred(args.signin_cred)
    if failure:
        return out(failure)
    # --engine legacy never needs the probe, so Ego Lite is not touched (the probe opens a setup window when onboarding is unfinished)
    if args.engine == "legacy":
        availability = ego_engine.EgoAvailability(False, "not_checked", None)
    else:
        availability = ego_engine.check_ego_availability()
    provider = credential.get("provider")
    decision = ego_engine.decide_engine(
        args.engine, availability, _has_signed_in_current_profile(project_root(args), provider))

    if decision.engine == "unavailable":
        return out({"ok": False, "code": "ego_unavailable", "action": "signin", "engine": "unavailable",
                    "reason": decision.reason,
                    "error": f"Ego Lite is not available ({decision.reason})",
                    "next": f"web signin --cred {args.signin_cred} --engine legacy  # or finish the Ego Lite setup first (open the app once)"})
    if decision.engine == "legacy":
        open_step = (f"web open --need login:{provider} --url <login url>" if decision.reason == "signed_in_profile"
                     else "web open --headed --url <login url>")
        return out({"ok": True, "code": "ok", "action": "signin", "engine": "legacy", "reason": decision.reason,
                    "summary": f"Using the current engine ({decision.reason})",
                    "next": f"{open_step}  # then follow the common flow in references/web-sign-in.md"})

    handoff, failure = ego_engine.build_signin_handoff(
        credential, credentials.resolve_login_policy(args.signin_cred))
    if failure:
        return out(failure)
    return out({"ok": True, "code": "ok", "action": "signin", "engine": "ego", "reason": decision.reason,
                "summary": "Sign in through Ego Lite with the information below (one Ego space for the goal)",
                "handoff": handoff,
                "next": f"Follow {EGO_GUIDE_POINTER}: never retry a failed password or code, and never switch engines after typing"})


def configure(p) -> None:
    # Separate dest — the web dispatcher tries to pull the password field early if it sees args.cred
    p.add_argument("--cred", dest="signin_cred", metavar="NAME", required=True,
                   help="Saved credential name (cred list)")
    p.add_argument("--engine", choices=ENGINE_CHOICES, default="auto",
                   help="auto: Ego Lite when available, else the current engine. ego: Ego Lite or fail. legacy: current engine")


ACTION = Action(name="signin", needs="nothing", run=execute, configure=configure, options=(),
                help="Pick the sign-in engine (Ego Lite when available) and hand over the stored sign-in information",
                example="web signin --cred google-work --engine auto")
