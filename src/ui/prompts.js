// 대화형 프롬프트 래핑 (.sh interactive_menu/choose_menu/ask_* 등가).
// node:readline 기반 자체 엔진 사용 (@clack/prompts 는 Windows TTY에서 Enter가 멈추는 버그로 제거).
// 취소(ESC/Ctrl+C)는 각 함수가 CANCEL 심볼을 반환 → 호출부가 정상 종료(exit 0) 처리.
import * as engine from "./readline-engine.js";
import { t } from "../i18n/index.js";

export const CANCEL = engine.CANCEL;

// 모드 선택 — 한국어 라벨, 내부 키 반환. 취소 시 CANCEL.
// update(#502): { from, to } — 기존 통합 레포로 판별된 경우. 맨 위에 업데이트 항목을 추가하고
// 기본 선택으로 둔다 (첫 항목 = 기본). 신규 레포(update 미전달)는 현행 5개 그대로.
export async function selectMode({ update = null } = {}) {
  const options = [];
  if (update) {
    const range = update.from ? `v${update.from} → v${update.to}` : `v${update.to}`;
    options.push({ value: "update", label: t("mode.update", { range: `v${range}` }) });
  }
  options.push(
    { value: "full", label: t("mode.full") },
    { value: "version", label: t("mode.version") },
    { value: "workflows", label: t("mode.workflows") },
    { value: "issues", label: t("mode.issues") },
    { value: "skills", label: t("mode.skills") },
  );
  return engine.select({ message: t("mode.prompt"), options });
}

// 프로젝트 확인 화면 메뉴 (계속/수정/취소).
export async function confirmProjectMenu() {
  return engine.select({
    message: t("confirm.prompt"),
    options: [
      { value: "continue", label: t("confirm.continue") },
      { value: "edit", label: t("confirm.edit") },
      { value: "cancel", label: t("confirm.cancel") },
    ],
  });
}

// 수정 메뉴 — 어떤 항목을 고칠지. showOptional=full/workflows에서만 nexus/secret 노출.
// axes(#498): applicableTargets(types) 결과 — 적용 불가 축의 항목은 숨긴다 (모바일 앱/basic 단독 등).
// null이면 기존처럼 전부 노출 (테스트 스텁 하위호환).
export async function editMenu({ showOptional = false, axes = null } = {}) {
  const options = [
    { value: "type", label: t("edit.type") },
    { value: "version", label: t("edit.version") },
    { value: "branch", label: t("edit.branch") },
  ];
  if (showOptional) {
    const hasDeploy = axes == null || axes.deploy.length > 0;
    const hasPublish = axes == null || axes.publish.length > 0;
    // #485 — 프로젝트 성격(intent): 재선택 시 배포/publish 축을 재유도한다. 축이 하나도 없으면 무의미 → 숨김.
    if (hasDeploy || hasPublish) options.push({ value: "intent", label: t("edit.intent") });
    // #483 — 항목별 격리: 한 축만 골라 그 축만 재질문한다 (통짜 "배포/Publish 방식" 분해)
    if (hasDeploy) options.push({ value: "deploy", label: t("edit.deploy") });
    if (hasPublish) options.push({ value: "publish", label: t("edit.publish") });
    options.push({ value: "code-review", label: t("edit.codeReview") });
    options.push({ value: "changelog", label: t("edit.changelog") });
    options.push({ value: "release-branch", label: t("edit.releaseBranch") });
    options.push({ value: "secret", label: t("edit.secret") });
  }
  options.push({ value: "done", label: t("edit.done") });
  return engine.select({ message: t("edit.prompt"), options });
}

// 타입 멀티선택.
export async function selectTypes(current = []) {
  const all = ["spring", "flutter", "react", "react-native", "react-native-expo", "node", "python", "basic"];
  return engine.multiselect({
    message: t("types.prompt"),
    options: all.map((t) => ({ value: t, label: t })),
    initialValues: current.length ? current : ["basic"],
    required: true,
  });
}

// 텍스트 입력 (빈 입력=기본값 유지).
export async function askText(message, defaultValue = "") {
  const v = await engine.text({ message, defaultValue });
  if (v === CANCEL) return CANCEL;
  return v === "" || v == null ? defaultValue : v;
}

// 예/아니오.
export async function askYesNo(message, initial = true) {
  return engine.confirm({ message, initialValue: initial });
}

// 배너·안내 출력.
export function intro(text) { engine.intro(text); }
export function outro(text) { engine.outro(text); }
export function note(text, title) { engine.note(text, title); }
export function cancelMessage(text = "취소했습니다.") { engine.cancelMessage(text); }

// ── #446 첫 화면 UI 5층 + SP2-C 대화형 계층 실물 io ─────────────────
// runInteractive는 io.<method>?.() 옵셔널 호출 — 테스트 스텁은 이 메서드들을 생략해
// 시각 층·env 질문을 건너뛴다 (실행 계약은 그대로).
import { printBanner as _printBanner } from "./banner.js";
import {
  printDetectionLog as _detLog, printAnalysisCard as _card,
  printIdeStatus as _ideStatus, printInstallKind as _installKind, collectIdeStatuses,
} from "./status-cards.js";
import { printSummary as _summary } from "./summary.js";
import { defaultIo } from "../core/ide/runner.js";

export function banner(info) { _printBanner(info); }
export function detectionLog(info) { _detLog(info); }
export function analysisCard(info) { _card(info); }
export function installKind(info) { _installKind(info); }
export function ideStatus() { _ideStatus(collectIdeStatuses(defaultIo())); }
export function summary(ctx, targetRoot) { _summary(ctx, targetRoot); }

// env 계획·경로 해석·충돌 메뉴가 쓰는 저수준 엔진 io (env-plan/paths-resolve의 io 계약)
export const engineIo = {
  select: engine.select,
  multiselect: engine.multiselect,
  text: engine.text,
  confirm: engine.confirm,
};
