"""gbrain-remote adapter: a `gbrain serve --http` brain over MCP (personal or team-shared, any number)
Capabilities come from tools/list, never assumed: put_page page by page, put_pages when exposed for several notes.
The token is read from the credential store by name and only placed in the Authorization header.
"""
from __future__ import annotations

import uuid

from .. import credentials, http_client, mcp_http, note_file
from .base import Adapter, check, write_result

TOKEN_FIELD = "token"
WRITE_TOOLS = ("put_page", "put_pages")
SEARCH_TOOLS = ("search", "query")
LIST_TOOLS = ("find_pages", "list_pages")
READ_TOOLS = ("get_page",)
LIST_PAGE_LIMIT = 100           # remote max per call
LIST_PAGE_ROUNDS = 20           # 2000 notes per project at most
BATCH_LIMIT = 50                # put_pages accepts 1-50 pages
NOT_FOUND_WORDS = ("not found", "page_not_found", "not_found", "no page")
STORE_TOKEN_COMMAND = ("python3 ~/.projectops/bin/projectops_cli.py launch cred set --name {name} --secret-field token "
                       "--prompt --json '{{\"kind\":\"token\",\"provider\":\"gbrain\",\"use_when\":\"brain {mcp} MCP\"}}'")


def _is_not_found(error_text: str) -> bool:
    lowered = (error_text or "").lower()
    return any(word in lowered for word in NOT_FOUND_WORDS)


class GbrainRemoteAdapter(Adapter):
    kind = "gbrain-remote"

    def _token(self) -> tuple[str | None, str]:
        """(token or None, state: stored | missing | unreadable); the value never leaves this adapter"""
        try:
            return credentials.read_secret(self.destination["token_cred"], TOKEN_FIELD), "stored"
        except credentials.CredentialError as error:
            return None, "unreadable" if error.code == "config_unreadable" else "missing"

    def _session(self, token: str) -> mcp_http.McpSession:
        session = mcp_http.McpSession(self.destination["mcp_url"], token, post=self.context.get("_post") or http_client.post_json)
        session.initialize()
        return session

    def _store_token_fix(self) -> str:
        return STORE_TOKEN_COMMAND.format(name=self.destination["token_cred"], mcp=self.destination["name"])

    def detect(self) -> dict:
        return {"available": bool(self.destination.get("mcp_url")), "token": self._token()[1]}

    def doctor(self, quick: bool = False) -> dict:
        destination = self.destination
        command = (f"MCP tools/call put_page at {destination.get('mcp_url_shown') or '<url>'} "
                   f"(Authorization: Bearer <token from credential '{destination['token_cred']}'>)")
        url = destination.get("mcp_url")
        if not url:
            return {"command": command, "checks": [check("mcp_url", "fail", f"no URL for {destination['name']} ({destination.get('url_origin')})",
                                                         "ask the brain admin for the URL; record it with setup --team-brain-url "
                                                         "or in your registry infra.brains.<name>.mcp_url", code="remote_url_unknown")]}
        post = self.context.get("_post") or http_client.post_json
        checks = []
        anonymous = post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": mcp_http.PROTOCOL_VERSION, "capabilities": {},
                                          "clientInfo": mcp_http.CLIENT_INFO}})
        anonymous_code = mcp_http.classify_status(anonymous["status"], anonymous["body"])
        if anonymous_code == "unreachable":
            checks.append(check("reachable", "fail", f"{destination['mcp_url_shown']} did not answer ({anonymous['error']})",
                                "check DNS, network, VPN or TLS for that host", code="remote_unreachable"))
            return {"checks": checks, "command": command}
        if anonymous_code == "proxy_refused":
            checks.append(check("proxy", "fail", "a proxy in front of the brain refused the request (Cloudflare 1010 or 403 page)",
                                f"allow the User-Agent '{http_client.USER_AGENT}' (or this IP) in the proxy rules",
                                code="proxy_refused"))
            return {"checks": checks, "command": command}
        if anonymous_code == "not_found":
            checks.append(check("endpoint", "fail", "the URL answers 404: wrong path or brain key",
                                "compare the URL with the brain admin's (it usually ends in /mcp)", code="unknown_brain"))
            return {"checks": checks, "command": command}
        if anonymous["status"] and 200 <= anonymous["status"] < 300:
            checks.append(check("auth_required", "warn", "the brain answers without a token: anyone can use it",
                                "tell the brain admin to require tokens"))
        else:
            checks.append(check("auth_required", "ok", f"answers {anonymous['status']} without a token"))
        token, token_state = self._token()
        if token_state != "stored":
            checks.append(check("token", "fail", f"no token stored under credential '{destination['token_cred']}' ({token_state})",
                                self._store_token_fix(), code="token_missing"))
            return {"checks": checks, "command": command}
        checks.append(check("token", "ok", f"token stored under '{destination['token_cred']}' (shown as <token>)"))
        try:
            session = self._session(token)
            tools = session.list_tool_names()
        except mcp_http.McpError as error:
            code = {"unauthorized": "token_rejected", "forbidden": "token_forbidden"}.get(error.code, f"mcp_{error.code}")
            fix = (self._store_token_fix() + "  # the stored token was rejected: store a new one" if error.code in
                   ("unauthorized", "forbidden") else "brain_cli.py doctor again; check the brain server logs")
            checks.append(check("initialize", "fail", http_client.mask_text(error.message, [token]), fix, code=code))
            return {"checks": checks, "command": command}
        capabilities = self._capabilities(tools, session.server_info)
        if not capabilities["write_tools"] and capabilities["request_tools"]:
            capabilities["write_probe"] = self._probe_write_tool(session)
            if capabilities["write_probe"] == "granted":
                capabilities["write_tools"] = ["put_page"]
        checks.append(check("initialize", "ok", f"MCP session open ({capabilities['server']})"))
        checks.append(self._scope_check(capabilities))
        return {"checks": checks, "command": command, "capabilities": capabilities}

    def _capabilities(self, tools: list[str], server_info: dict) -> dict:
        names = set(tools)
        return {"server": f"{server_info.get('name') or 'mcp'} {server_info.get('version') or ''}".strip(),
                "tool_count": len(tools),
                "write_tools": [name for name in WRITE_TOOLS if name in names],
                "search_tools": [name for name in SEARCH_TOOLS if name in names],
                "list_tools": [name for name in LIST_TOOLS if name in names],
                "read_tools": [name for name in READ_TOOLS if name in names],
                "request_tools": "request_tools" in names,
                "batch": "put_pages" in names}

    @staticmethod
    def _probe_write_tool(session) -> str:
        """request_tools(put_page) > granted (write token) | refused (read token gets an empty list) | unknown"""
        try:
            answer = session.call_tool("request_tools", {"tools": ["put_page"]})
        except mcp_http.McpError:
            return "unknown"
        data = answer.get("data")
        if answer.get("is_error") or not isinstance(data, dict) or not isinstance(data.get("tools"), list):
            return "unknown"
        return "granted" if any(isinstance(tool, dict) and tool.get("name") == "put_page" for tool in data["tools"]) \
            else "refused"

    def _scope_check(self, capabilities: dict) -> dict:
        is_write_target = self.destination.get("is_write_target")
        if capabilities["write_tools"]:
            return check("scope", "ok", f"write tools exposed: {', '.join(capabilities['write_tools'])}; "
                                        f"search: {', '.join(capabilities['search_tools']) or 'none listed'}", scope="write")
        if capabilities["request_tools"] and capabilities.get("write_probe") != "refused":
            return check("scope", "warn" if is_write_target else "ok",
                         "no write tool advertised; request_tools may unlock put_page (write tries it)",
                         "if write fails with an unknown tool, ask the admin for a write-scoped token or a wider surface",
                         scope="unknown")
        if is_write_target:
            return check("scope", "fail", "this token only reads (no put_page): notes cannot be written here",
                         "ask the brain admin for a write-scoped token, or switch this brain to read via sync "
                         "(setup --team-write sync)", code="read_only_token", scope="read")
        return check("scope", "ok", "read-only token (enough: this brain is read via sync)", scope="read")

    def _revision(self, session: mcp_http.McpSession, slug: str) -> tuple[str | None, str | None]:
        """(revision or None when the page does not exist, error code)"""
        try:
            answer = session.call_tool("get_page", {"slug": slug, "body": "none"})
        except mcp_http.McpError as error:
            return (None, None) if _is_not_found(error.message) else (None, error.code)
        if answer["is_error"]:
            return (None, None) if _is_not_found(answer["text"]) else (None, "get_page_error")
        return str((answer["data"] or {}).get("revision") or "") or None, None

    def _put_one(self, session: mcp_http.McpSession, note: dict) -> dict:
        revision, error = self._revision(session, note["slug"])
        if error:
            return write_result(self.destination, "failed", f"get_page failed ({error})", code=error)
        arguments = {"slug": note["slug"], "content": note["content"], "content_origin": "inferred",
                     "reason": "pro-brain note", "request_id": str(uuid.uuid4())}
        if revision:
            arguments["expected_revision"] = revision
        try:
            answer = session.call_tool("put_page", arguments)
        except mcp_http.McpError as error:
            return write_result(self.destination, "failed", f"put_page failed: {error.message}", code=f"mcp_{error.code}")
        if answer["is_error"]:
            text = http_client.mask_text(answer["text"][:300], [])
            code = "read_only_token" if any(word in text.lower() for word in ("scope", "forbidden", "read-only", "read only")) else \
                ("write_tool_hidden" if "unknown tool" in text.lower() or "not found" in text.lower() else "put_page_error")
            return write_result(self.destination, "failed", f"put_page refused: {text}", code=code,
                                fix="brain_cli.py doctor --to " + self.destination["id"])
        data = answer["data"] or {}
        outcome = "unchanged" if data.get("noop") is True else ("updated" if revision else "written")
        return write_result(self.destination, outcome, f"{outcome} page {note['slug']}", slug=note["slug"],
                            revision=data.get("revision"))

    def write(self, note: dict) -> dict:
        return self.write_many([note])[0]

    def write_many(self, notes: list[dict]) -> list[dict]:
        token, state = self._token()
        if state != "stored":
            return [write_result(self.destination, "failed", f"no token under '{self.destination['token_cred']}'",
                                 code="token_missing", fix=self._store_token_fix()) for _ in notes]
        try:
            session = self._session(token)
        except mcp_http.McpError as error:
            return [write_result(self.destination, "failed", http_client.mask_text(error.message, [token]),
                                 code=f"mcp_{error.code}", fix="brain_cli.py doctor --to " + self.destination["id"]) for _ in notes]
        tools = set()
        if len(notes) > 1:
            try:
                tools = set(session.list_tool_names())
            except mcp_http.McpError:
                tools = set()
        if len(notes) > 1 and "put_pages" in tools:
            batched = self._put_batch(session, notes)
            if batched is not None:
                return batched
        return [self._put_one(session, note) for note in notes]

    def _put_batch(self, session: mcp_http.McpSession, notes: list[dict]) -> list[dict] | None:
        """put_pages in chunks of 50; None falls back to page by page (blocked tool, unknown answer shape)"""
        results = []
        for start in range(0, len(notes), BATCH_LIMIT):
            chunk = notes[start:start + BATCH_LIMIT]
            pages = []
            for note in chunk:
                revision, error = self._revision(session, note["slug"])
                if error:
                    return None
                page = {"slug": note["slug"], "content": note["content"], "reason": "pro-brain note"}
                if revision:
                    page["expected_revision"] = revision
                pages.append((page, bool(revision)))
            try:
                answer = session.call_tool("put_pages", {"pages": [page for page, _ in pages], "request_id": str(uuid.uuid4())})
            except mcp_http.McpError:
                return None
            if answer["is_error"]:
                return None
            results += [write_result(self.destination, "updated" if existed else "written",
                                     f"{'updated' if existed else 'written'} page {page['slug']} (batch)", slug=page["slug"])
                        for page, existed in pages]
        return results

    def search_hint(self) -> str:
        return f"search the MCP '{self.destination['name']}' (search / query tools)"

    def note_ids(self) -> tuple[set[str] | None, str]:
        token, state = self._token()
        if state != "stored" or not self.destination.get("mcp_url"):
            return None, f"cannot read {self.destination['name']} (token {state}, url {'set' if self.destination.get('mcp_url') else 'unknown'})"
        prefix = note_file.project_prefix(self.context["project"])
        try:
            session = self._session(token)
            slugs, offset = [], 0
            for _ in range(LIST_PAGE_ROUNDS):
                answer = session.call_tool("list_pages", {"slug_prefix": prefix, "limit": LIST_PAGE_LIMIT,
                                                          "offset": offset, "sort": "slug"})
                if answer["is_error"]:
                    return None, "list_pages refused"
                data = answer["data"]
                rows = data if isinstance(data, list) else (data or {}).get("pages") or []
                slugs += [row.get("slug", "") for row in rows if isinstance(row, dict)]
                if len(rows) < LIST_PAGE_LIMIT:
                    break
                offset += LIST_PAGE_LIMIT
        except mcp_http.McpError as error:
            return None, http_client.mask_text(error.message, [token])
        return {slug.rsplit("/", 1)[-1] for slug in slugs if slug}, f"{self.destination['name']} pages {prefix}*"

    def backup_hint(self) -> str | None:
        prefix = note_file.project_prefix(self.context["project"])
        return (f"on the brain host: gbrain export --slug-prefix {prefix} --dir ~/gbrain-backup/{note_file.slug_part(self.context['project'])}"
                "/$(date +%Y%m%d)   # scheduled daily; export never overwrites")
