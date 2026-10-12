"""명령들이 함께 쓰는 아래층 — 결과 내기 · 상태 · 기기 · 브라우저 · 프로세스.

이 층은 `commands/` 를 import 하지 않는다. 의존은 언제나 아래로만 흐른다: commands → runtime.
`sys.platform` 로 갈리는 동작은 `procs.py` 한 곳에만 둔다.
"""
