"""Docker 정리: 사실 수집 > 순서 고정 삭제

순서: 미사용 볼륨 목록을 먼저 찍음 > 그 목록만 삭제 > 이름을 댄 정지 컨테이너 삭제 > 미사용 이미지·빌드 캐시
컨테이너 삭제로 새로 미사용이 된 볼륨은 지우지 않고 보고만 (그 컨테이너가 쓰던 데이터일 수 있음)
"""
from __future__ import annotations

import json
import shutil

from . import shell, sizes


def _docker(*arguments: str, timeout_seconds: int = 120) -> tuple[int, str]:
    code, out, error = shell.run(["docker", *arguments], timeout_seconds=timeout_seconds)
    return code, out if code == 0 else error


def _json_lines(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def availability() -> dict | None:
    """docker 사용 불가 사유 (사용 가능하면 None)"""
    if not shutil.which("docker"):
        return {"ok": True, "code": "docker_missing", "summary": "Docker is not installed"}
    code, _ = _docker("info", "--format", "{{.ServerVersion}}", timeout_seconds=20)
    if code != 0:
        return {"ok": True, "code": "docker_not_running", "summary": "Docker is installed but the engine is not running"}
    return None


def dangling_volume_names() -> list[str]:
    _, out = _docker("volume", "ls", "--filter", "dangling=true", "--format", "{{.Name}}")
    return [name for name in out.splitlines() if name.strip()]


def facts() -> dict:
    unavailable = availability()
    if unavailable:
        return unavailable
    _, usage = _docker("system", "df", "--format", "{{json .}}")
    _, containers = _docker("ps", "-a", "--filter", "status=exited", "--filter", "status=created",
                            "--format", "{{json .}}")
    stopped = [{"name": row.get("Names"), "image": row.get("Image"), "status": row.get("Status"),
                "size": row.get("Size")} for row in _json_lines(containers)]
    dangling = dangling_volume_names()
    return {"ok": True, "code": "ok", "usage": _json_lines(usage), "stopped_containers": stopped,
            "dangling_volumes": dangling, "dangling_volume_count": len(dangling),
            "summary": f"{len(stopped)} stopped containers, {len(dangling)} unused volumes",
            "next": "docker --volumes --images [--containers NAME ...] --yes  # containers only by name"}


def clean(should_remove_volumes: bool, should_remove_images: bool, container_names: list[str], is_confirmed: bool) -> dict:
    unavailable = availability()
    if unavailable:
        return unavailable
    # 1) 지우기 전 미사용 볼륨 목록 고정
    volumes_before = dangling_volume_names() if should_remove_volumes else []
    plan = {"volumes": volumes_before, "containers": container_names, "images_and_build_cache": should_remove_images}
    if not is_confirmed:
        return {"ok": True, "code": "dry_run", "plan": plan,
                "summary": f"Would remove {len(volumes_before)} volumes, {len(container_names)} containers"
                           f"{', unused images and build cache' if should_remove_images else ''}. Re-run with --yes"}
    free_before = sizes.free_bytes()
    steps = []
    # 2) 고정 목록의 볼륨만
    for name in volumes_before:
        code, out = _docker("volume", "rm", name)
        steps.append({"step": "volume", "target": name, "ok": code == 0, "detail": out.strip()[-200:]})
    # 3) 이름 댄 정지 컨테이너만 (실행 중이면 docker 가 거절)
    for name in container_names:
        code, out = _docker("rm", name)
        steps.append({"step": "container", "target": name, "ok": code == 0, "detail": out.strip()[-200:]})
    # 4) 이미지·빌드 캐시 (남은 컨테이너가 쓰는 이미지는 docker 가 남김)
    if should_remove_images:
        for arguments in (("image", "prune", "-a", "-f"), ("builder", "prune", "-f")):
            code, out = _docker(*arguments, timeout_seconds=900)
            steps.append({"step": " ".join(arguments[:2]), "ok": code == 0, "detail": out.strip()[-200:]})
    newly_unused = sorted(set(dangling_volume_names()) - set(volumes_before))
    return {"ok": all(step["ok"] for step in steps), "code": "cleaned", "steps": steps,
            "newly_unused_volumes": newly_unused,
            "freed_gb": sizes.to_gigabytes(max(sizes.free_bytes() - free_before, 0)),
            "summary": f"Done. {len(newly_unused)} volumes became unused after container removal and were kept",
            "next": "show newly_unused_volumes to the user before any further volume removal" if newly_unused else None}
