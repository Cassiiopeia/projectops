// IDE 어댑터 공통 계약 (확장 포인트의 핵심).
//
// 새 IDE(에디터/에이전트 CLI)를 지원하려면 이 shape을 만족하는 객체 하나를
// src/core/ide/adapters/<name>.js 에 만들고 registry.js 배열에 추가하기만 하면 된다.
// 오케스트레이터(commands/skills.js)는 어댑터의 필드만 알고, 개별 IDE 로직은 전혀 모른다.
//
// @typedef {Object} IdeStatus
//   installed: boolean       설치돼 있는가
//   version:   string|null   설치 버전(알 수 있으면)
//   cliMissing: boolean      전용 CLI가 없어 설치 불가한 상태인가 (안내만 가능)
//   note:      string        상태 표시줄에 덧붙일 짧은 메모(선택)
//
// @typedef {Object} IdeAdapter
//   id:      string   내부 고유키 (예: "claude"). 라우팅·preselect에 사용
//   label:   string   사람에게 보이는 이름 (예: "Claude Code")
//   order:   number   상태·메뉴 표시 순서 (작을수록 먼저)
//   detect(io): IdeStatus                     현재 설치 상태
//   apply(io, ctx): boolean                   설치 또는 업데이트(멱등). 성공 true
//   remove(io, ctx): boolean                  제거(미설치면 no-op, true)
//   manualHint(io): string                    CLI 없을 때 보여줄 수동 설치 명령(선택)
//
// io = runner.defaultIo() 또는 테스트 stub: { which, run, home, log, projectopsHome?(없으면 home/.projectops) }
// ctx = { templateVersion, sourceSkillsDir } — 버전 표기·Cursor 복사 소스 등 공용 컨텍스트
//
// 규칙:
//  - apply/remove/detect는 예외를 던지지 않는다(내부에서 흡수). 실패는 log + false로 표현.
//  - CLI 미존재는 에러가 아니라 cliMissing 상태 + manualHint로 안내한다.
//  - 어댑터는 io를 통해서만 외부와 상호작용한다(직접 spawnSync/console 금지) — 테스트 가능성.

// 어댑터가 최소 계약을 지키는지 개발 중 검증하는 헬퍼(런타임 방어).
export function assertAdapter(a) {
  for (const k of ["id", "label", "detect", "apply", "remove"]) {
    if (a[k] == null) throw new Error(`IDE 어댑터 '${a?.id || "?"}'에 필수 필드 '${k}'가 없습니다`);
  }
  return a;
}
