"""Engine choice for `web signin` and the Ego Lite hand-over block (#1231)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills" / "pro-launch" / "scripts"))

from pro_launch.runtime import ego_engine  # noqa: E402

EGO_COMMAND = "/usr/local/bin/ego-browser"
PROBE_COMMAND = [EGO_COMMAND, "nodejs", "-e", "console.log('ego-browser ready')"]
ONBOARDING_MESSAGE = "Please complete the onboarding process first. A setup window has opened."


def _fake_probe(exit_code=0, stdout="ego-browser ready", error=None):
    """Probe stand-in that records how it was called."""
    calls = []

    def run_probe(command, **options):
        calls.append((command, options))
        if error:
            raise error
        return subprocess.CompletedProcess(command, exit_code, stdout=stdout, stderr="")

    run_probe.calls = calls
    return run_probe


@pytest.mark.parametrize(
    "requested, command, has_display, probe_options, is_signed_in, expected_engine, expected_reason, expected_probe_calls",
    [
        ("auto", EGO_COMMAND, True, {}, False, "ego", "ready", 1),
        ("auto", EGO_COMMAND, True, {}, True, "legacy", "signed_in_profile", 1),
        ("auto", None, True, {}, False, "legacy", "ego_not_found", 0),
        ("auto", EGO_COMMAND, True, {"exit_code": 1, "stdout": ONBOARDING_MESSAGE}, False, "legacy", "ego_not_onboarded", 1),
        ("auto", EGO_COMMAND, False, {}, False, "legacy", "ego_no_display", 0),
        ("auto", EGO_COMMAND, True, {"error": subprocess.TimeoutExpired("ego-browser", 20)}, False, "legacy", "ego_probe_timeout", 1),
        ("ego", None, True, {}, False, "unavailable", "ego_not_found", 0),
        ("legacy", EGO_COMMAND, True, {}, False, "legacy", "requested", 1),
    ],
)
def test_engine_decision_table(requested, command, has_display, probe_options, is_signed_in,
                               expected_engine, expected_reason, expected_probe_calls):
    run_probe = _fake_probe(**probe_options)
    availability = ego_engine.check_ego_availability(
        find_command=lambda: command, check_display=lambda: has_display, run_probe=run_probe)
    decision = ego_engine.decide_engine(requested, availability, is_signed_in)

    assert (decision.engine, decision.reason) == (expected_engine, expected_reason)
    assert len(run_probe.calls) == expected_probe_calls
    if expected_probe_calls:
        probe_command, options = run_probe.calls[0]
        assert probe_command == PROBE_COMMAND
        assert options["timeout"] == ego_engine.EGO_PROBE_TIMEOUT_SECONDS == 20


def test_signin_handoff_fields():
    credential = {
        "name": "demo", "kind": "login", "provider": "google", "account": "demo@example.invalid",
        "password": "demo-password", "two_factor": "phone approval", "use_when": "demo only",
        "notes": "secret note",
    }
    policy = {"trust_device": "always"}

    handoff, error = ego_engine.build_signin_handoff(credential, policy)
    assert error is None
    assert set(handoff) == set(ego_engine.HANDOFF_FIELD_NAMES)
    assert handoff["second_factor"] == "phone approval"
    assert handoff["login_policy"] == policy
    assert "secret note" not in json.dumps(handoff)

    for missing in ("password", "account"):
        incomplete = {key: value for key, value in credential.items() if key != missing}
        handoff, error = ego_engine.build_signin_handoff(incomplete, policy)
        assert handoff is None
        assert error["code"] == "cred_field_missing"

    without_provider = {key: value for key, value in credential.items() if key != "provider"}
    handoff, error = ego_engine.build_signin_handoff(without_provider, policy)
    assert error is None and handoff["provider"] is None
