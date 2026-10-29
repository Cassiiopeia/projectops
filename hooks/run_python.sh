#!/bin/sh
# 훅 공통 파이썬 실행기: python3 > python > py -3 순으로 실제 실행되는 것을 골라 인자 그대로 넘김 (#987)
# Windows python3 는 Store 스텁일 수 있음 (Python 출력 후 exit 49) > -c 로 실행 확인 후 선택
# 쓸 파이썬이 없으면 조용히 exit 0 (훅 실패로 매 도구 호출을 막지 않음)
# POSIX sh 전용 (macOS bash 3.2·Git Bash 공통). extras 사본은 scripts/sync_extras.py 가 생성
for candidate in python3 python; do
  candidate_path=$(command -v "$candidate" 2>/dev/null) || continue
  # 확인 실행이 훅 stdin(JSON)을 먹지 않게 /dev/null 연결
  if "$candidate_path" -c "import sys; sys.exit(0)" </dev/null >/dev/null 2>&1; then
    exec "$candidate_path" "$@"
  fi
done
# Windows 파이썬 런처 (py.exe): WindowsApps 스텁이 PATH 앞에 있어 위 둘이 다 스텁일 때
launcher_path=$(command -v py 2>/dev/null) || exit 0
if "$launcher_path" -3 -c "import sys; sys.exit(0)" </dev/null >/dev/null 2>&1; then
  exec "$launcher_path" -3 "$@"
fi
exit 0
