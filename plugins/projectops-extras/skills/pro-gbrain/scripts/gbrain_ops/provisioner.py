"""Brain server clients. One contract (references/provisioner-contract.md); `control-tower` speaks it over HTTP.
Teams without a provisioner get the manual server steps instead. Secrets (admin key, writer password, tokens) stay in
memory or 600 files and never reach the JSON output.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from . import common, registry_store

REQUEST_TIMEOUT_SECONDS = 180   # create runs gbrain init and installs a service on the server
USER_AGENT = "projectops-pro-gbrain/1"
SUPPORTED_TYPES = ("control-tower",)
READ_ONLY_SCOPE_PRESET = "read_only"
# Server error codes > what the user does next (unknown codes fall back to the server's own next_step)
NEXT_STEP_BY_CODE = {
    "invalid_project": "pass --project with 2-20 lower case letters or digits",
    "reserved_project": "pass another --project key",
    "team_brain_not_found": "run add (or repair) first so the server creates the brain",
    "team_database_not_empty_unknown": "the database holds data the server cannot classify: the brain admin checks it by hand; nothing was dropped",
}


class ControlTowerProvisioner:
    """HTTP client for the reference provisioner (nginx path + admin key header)"""

    def __init__(self, name: str, block: dict, admin_key: str):
        self.name = name
        self.block = block
        self.base_url = str(block.get("base_url") or "").rstrip("/")
        self.auth_header = block.get("auth_header") or "X-API-Key"
        self.supports_dry_run = bool(block.get("supports_dry_run"))
        self._admin_key = admin_key
        if not self.base_url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
            raise common.StepError("provisioner_bad_url", "provisioner base_url must be https (or a local test address)",
                                   "fix infra.brains.<name>.provisioner.base_url in the registry")

    # ---------- contract ----------
    def create(self, project: str, dry_run: bool = False) -> dict:
        if dry_run and not self.supports_dry_run:
            # Never send dry_run to a server that may ignore it and create for real
            return {"dry_run_supported": False}
        body = {"project": project, **({"dry_run": True} if dry_run else {})}
        return self._request("POST", "/gbrain/teams", body)

    def list_brains(self) -> list:
        return self._request("GET", "/gbrain/teams").get("brains") or []

    def status(self, project: str) -> dict:
        return self._request("GET", f"/gbrain/teams/{urllib.parse.quote(project)}/status")

    def issue_read_only_token(self, project: str, token_name: str) -> dict:
        """> {token_id, secret, mcp_url, mcp_server_name}; the caller keeps secret in memory or a 600 file only"""
        response = self._request("POST", "/gbrain/tokens",
                                 {"brain": project, "name": token_name, "scope_preset": READ_ONLY_SCOPE_PRESET})
        token = response.get("token") or {}
        return {"token_id": token.get("id"), "scopes": token.get("scopes"), "secret": response.get("secret"),
                "mcp_url": response.get("mcp_url"), "mcp_server_name": response.get("mcp_server_name")}

    def revoke_token(self, project: str, token_id: str) -> dict:
        return self._request("POST", f"/gbrain/tokens/{urllib.parse.quote(str(token_id))}/revoke", {"brain": project})

    # ---------- transport ----------
    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT, self.auth_header: self._admin_key}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return self._parse(response.read())
        except urllib.error.HTTPError as error:
            payload = self._parse(error.read(), allow_error=True)
            code = payload.get("code") or f"provisioner_http_{error.code}"
            if error.code in (401, 403) and not payload.get("code"):
                code = "provisioner_auth_failed"
            raise common.StepError(
                code, common.mask(str(payload.get("error") or payload.get("message") or f"HTTP {error.code}"), [self._admin_key]),
                payload.get("next_step") or NEXT_STEP_BY_CODE.get(code)
                or ("check the admin credential the registry names" if code == "provisioner_auth_failed" else "check the brain server logs"),
                {"http_status": error.code, "steps": payload.get("steps")})
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise common.StepError("provisioner_unreachable", f"brain server did not answer: {type(error).__name__}",
                                   "check the network or VPN and the provisioner base_url")

    @staticmethod
    def _parse(raw: bytes, allow_error: bool = False) -> dict:
        try:
            payload = json.loads(raw.decode("utf-8", "replace") or "{}")
        except ValueError:
            if allow_error:
                return {}
            raise common.StepError("provisioner_bad_response", "brain server answered with something other than JSON",
                                   "check base_url points at the provisioner API")
        return payload if isinstance(payload, dict) else {}


def open_provisioner(section: dict | None, name: str | None = None):
    """Configured provisioner client, or None when the registry declares none (manual server steps apply)"""
    provisioner_name, block = registry_store.find_provisioner(section, name)
    if not block:
        return None
    kind = block.get("type")
    if kind not in SUPPORTED_TYPES:
        raise common.StepError("provisioner_type_unsupported", f"provisioner type '{kind}' is not supported",
                               f"use one of {', '.join(SUPPORTED_TYPES)} or follow the manual server steps")
    return ControlTowerProvisioner(provisioner_name, block, registry_store.read_admin_key(block))


def manual_server_steps(project: str) -> list[str]:
    """What a brain admin does by hand when no provisioner is configured (mirrors the contract's create)"""
    return [
        f"Create a Postgres database for the team brain (e.g. gbrain_{project}) with pgvector, and a writer role that owns it",
        "Run `gbrain init --url <writer connection>` once for that database on the brain server",
        f"Run `gbrain serve --http` for it as a service on a private port, behind HTTPS (e.g. https://<host>/team/{project}/mcp)",
        "Issue read-only tokens per teammate with the brain's admin tools (gbrain mcp admin)",
        f"Then run: gbrain_cli.py add --mode team --mcp-url https://<host>/team/{project}/mcp --mcp-name gbrain-{project}",
    ]
