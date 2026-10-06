<!-- SUH-ISSUE-HELPER -->

<!-- Guide by SUH-LAB (구버전 워크플로우 호환용 표식) -->

Guide by ProjectOps
---

### 브랜치
```
20261007_#1_테스트_이슈
```

### 커밋 메시지
```
테스트 이슈 : feat : {변경 사항} https://x/1
```

<details>
<summary>💡 왜 이 브랜치명을 써야 하나요?</summary>

이 브랜치명 형식(`YYYYMMDD_#이슈번호_제목`)을 쓰면 아래 기능이 자동으로 연동됩니다:
- `@projectops app build` 댓글 빌드 — 이 댓글의 브랜치를 자동 인식해서 빌드
- 테스트 APK 빌드 — 브랜치의 `#이슈번호`로 이슈 정보를 빌드 노트에 자동 포함
- 테스트 TestFlight 빌드 — 브랜치의 `#이슈번호`로 이슈 정보를 자동 연동
- 커밋/보고서/리뷰 스킬 — 브랜치·worktree 폴더명에서 이슈 번호를 자동 추출해 커밋 메시지·보고서 완성

다른 형식의 브랜치명을 쓰면 위 자동화가 동작하지 않습니다.
</details>

<!-- SUH-ISSUE-HELPER -->