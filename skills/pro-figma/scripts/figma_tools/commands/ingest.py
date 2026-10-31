"""ingest: 하네스가 저장한 MCP 결과 파일 > 덤프 추출 > 저장 + 변경 확인용 메타 기록"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from common.emit import emit
from figma_tools.dump_reader import _load_dump
from figma_tools.figma_auth import fetch_file_state, find_token

META_SUFFIX = ".meta.json"
# 덤프 최상위에 이 키 중 하나는 있어야 덤프로 인정한다 (래퍼를 추측해 통과시키지 않는다)
_DUMP_KEYS = ("nodes", "globalVars", "metadata")


def _text_blocks(value) -> str | None:
    """[{type: text, text}] 또는 {content: [...]} 래퍼의 본문을 이어 붙인다. 아니면 None."""
    blocks = value.get("content") if isinstance(value, dict) else value
    if not isinstance(blocks, list) or not blocks:
        return None
    if not all(isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
               for b in blocks):
        return None
    return "\n".join(b["text"] for b in blocks)


def _is_dump(data) -> bool:
    return isinstance(data, dict) and any(k in data for k in _DUMP_KEYS)


def extract_dump(raw: str, scratch: Path) -> tuple[str | None, str | None, str | None]:
    """(덤프 본문, 확장자, 실패 사유). 래퍼는 한 겹만 벗긴다 — 모르는 모양은 사유만 돌려준다."""
    text = raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    if parsed is not None:
        if _is_dump(parsed):
            return raw, "json", None
        inner = _text_blocks(parsed)
        if inner is None:
            return None, None, "JSON without dump keys (nodes, globalVars, metadata) or text blocks"
        text = inner
    scratch.write_text(text, encoding="utf-8")
    data, err = _load_dump(scratch)
    if err:
        return None, None, err[1]
    if not _is_dump(data):
        return None, None, "text is neither a Figma dump nor a known wrapper"
    return text, ("json" if text.lstrip().startswith(("{", "[")) else "yaml"), None


def count_nodes(data) -> int:
    """덤프의 노드 수 (id 를 가진 dict). nodes 아래 children 까지 센다."""
    def walk(value) -> int:
        if isinstance(value, dict):
            own = 1 if "id" in value and "name" in value else 0
            return own + sum(walk(v) for v in value.values())
        if isinstance(value, list):
            return sum(walk(v) for v in value)
        return 0
    return walk(data.get("nodes") if isinstance(data, dict) else None)


def cmd_ingest(args) -> int:
    source = Path(args.source)
    if not source.is_file():
        return emit({"ok": False, "code": "source_not_found",
                     "error": f"Source file not found: {args.source}",
                     "hint": "Pass the file path the harness saved the get_figma_data result to"})
    dump_dir = Path(args.dump_dir)
    try:
        dump_dir.mkdir(parents=True, exist_ok=True)
        raw = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return emit({"ok": False, "code": "source_unreadable", "error": str(e)})

    text, ext, reason = extract_dump(raw, dump_dir / ".ingest-probe.tmp")
    (dump_dir / ".ingest-probe.tmp").unlink(missing_ok=True)
    if text is None:
        return emit({"ok": False, "code": "unknown_wrapper", "error": reason,
                     "hint": "Not guessing the format. Save the get_figma_data result as a file and pass it, "
                             "or report the wrapper shape so it can be supported"})

    node_slug = (args.node or "file").replace(":", "-")
    target = dump_dir / f"figma-{args.file_key}-{node_slug}.{ext}"
    target.write_text(text, encoding="utf-8")
    data, err = _load_dump(target)
    if err:
        return emit({"ok": False, "code": err[0], "error": err[1], "hint": err[2]})

    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    last_modified, version, last_modified_source = metadata.get("lastModified"), metadata.get("version"), "dump"
    warnings = []
    if not last_modified:
        token, _ = find_token()
        state = fetch_file_state(args.file_key, token) if token else {"ok": False}
        if state.get("ok"):
            last_modified, version, last_modified_source = state["lastModified"], state["version"], "rest"
        else:
            last_modified_source = None
            warnings.append({"code": "last_modified_missing",
                             "message": "The dump has no lastModified and Figma could not be asked; "
                                        "check-fresh will report unknown until a token is registered and ingest is re-run"})

    meta = {"file_key": args.file_key, "node_id": args.node, "last_modified": last_modified,
            "version": version, "last_modified_source": last_modified_source,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "source": str(source),
            "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    meta_path = Path(str(target) + META_SUFFIX)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    node_arg = f" --node {args.node}" if args.node else ""
    return emit({"path": str(target), "meta_path": str(meta_path), "node_count": count_nodes(data),
                 "file_key": args.file_key, "node_id": args.node, "last_modified": last_modified,
                 "version": version, "last_modified_source": last_modified_source, "warnings": warnings,
                 "summary": f"Saved the dump to {target} ({count_nodes(data)} nodes)",
                 "next": f"coverage --dump {target}{node_arg}"})
