// github-script 본문을 가짜 github/context/core 로 실행 > 게시 호출·출력을 JSON 으로 (#769 댓글 회귀 검사용)
// 입력(stdin): [{script, env, apiFail}, ...] 한 번에 여러 개 (node 를 스텝마다 띄우면 느리다)
// 시각 고정, API 응답은 어떤 속성 접근도 받아 주는 값 > 기존 스크립트와 새 스크립트가 같은 경로를 탄다
// node --test 가 test/ 아래 .cjs 를 테스트 파일로 실행함 > stdin 대기로 CI 가 멈춤. 테스트 실행기 안이면 바로 종료
if (process.env.NODE_TEST_CONTEXT) process.exit(0);

const fs = require('fs');

const FIXED_NOW = 1700000000000;
const RealDate = Date;
class FixedDate extends RealDate {
  constructor(...args) { if (args.length) super(...args); else super(FIXED_NOW); }
  static now() { return FIXED_NOW; }
}
// 로케일 날짜 문구는 Node·ICU 버전마다 다름 (오전 <-> AM) > 호출 인자를 담은 고정 문구로
for (const method of ['toLocaleString', 'toLocaleDateString', 'toLocaleTimeString']) {
  FixedDate.prototype[method] = function (locales, options) {
    return `[${method} ${JSON.stringify(locales ?? null)} ${JSON.stringify(options ?? null)}]`;
  };
}
global.Date = FixedDate;

// 어떤 속성·호출·문자열 변환도 받아 주는 값
function universal(path) {
  const fn = function () {};
  return new Proxy(fn, {
    get(_target, prop) {
      if (prop === Symbol.toPrimitive) return (hint) => (hint === 'number' ? 1 : 'U');
      if (prop === 'then') return undefined;
      if (prop === Symbol.iterator) return function* () {};
      if (prop === 'length') return 0;
      if (prop === 'toString' || prop === 'valueOf' || prop === 'toJSON') return () => 'U';
      return universal(`${path}.${String(prop)}`);
    },
    apply() { return universal(`${path}()`); },
  });
}

// 목록 API 는 빈 배열 (기존 댓글 없음 경로)
function apiData(method) {
  if (/^list/i.test(method)) return [];
  return universal('data');
}

async function runTask(task) {
  const calls = [];
  const outputs = {};
  const failed = [];
  const github = new Proxy({}, {
    get(_target, namespace) {
      if (namespace === 'rest') {
        return new Proxy({}, {
          get(_t2, group) {
            return new Proxy({}, {
              get(_t3, method) {
                return async (args) => {
                  calls.push({
                    api: `${String(group)}.${String(method)}`,
                    args: JSON.parse(JSON.stringify(args || {}, (k, v) => (typeof v === 'function' ? 'U' : v))),
                  });
                  // 읽기 호출만 404 로 실패 > 오류 댓글 경로 (쓰기 호출은 성공)
                  if (task.apiFail && /^(get|list|check)/.test(String(method))) {
                    throw Object.assign(new Error('Not Found'), { status: 404 });
                  }
                  return { data: apiData(String(method)), status: 200 };
                };
              },
            });
          },
        });
      }
      if (namespace === 'paginate') return async () => [];
      return universal(`github.${String(namespace)}`);
    },
  });
  const summary = new Proxy({}, {
    get(_target, prop) {
      if (prop === 'write') return async () => summary;
      return () => summary;
    },
  });
  const core = {
    setOutput: (key, value) => { outputs[key] = String(value); },
    setFailed: (message) => failed.push(String(message)),
    info() {}, warning() {}, error() {}, notice() {}, debug() {},
    exportVariable() {}, getInput: () => '',
    summary,
  };
  const context = {
    repo: { owner: 'o', repo: 'r' },
    issue: { owner: 'o', repo: 'r', number: 7 },
    payload: universal('payload'),
    runId: 999, runNumber: 5, sha: 'abcdef1234567', ref: 'refs/heads/main', eventName: 'repository_dispatch',
    actor: 'actor', serverUrl: 'https://github.com', workflow: 'wf', job: 'job',
  };
  const savedEnv = process.env;
  process.env = { ...savedEnv, ...task.env };
  const silent = { log() {}, error() {}, warn() {}, info() {} };
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  let error = null;
  try {
    const body = new AsyncFunction('github', 'context', 'core', 'require', 'process', 'console', 'exec', 'glob', 'io', task.script);
    await body(github, context, core, require, process, silent, universal('exec'), universal('glob'), universal('io'));
  } catch (e) {
    error = String((e && e.message) || e);
  } finally {
    process.env = savedEnv;
  }
  return { calls, outputs, failed, error };
}

(async () => {
  const tasks = JSON.parse(fs.readFileSync(0, 'utf8'));
  const results = [];
  for (const task of tasks) results.push(await runTask(task));
  process.stdout.write(JSON.stringify(results));
})();
