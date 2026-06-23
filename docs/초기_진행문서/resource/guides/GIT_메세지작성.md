# Commit 가이드
- 하나의 Commit은 하나의 작업이나 변경 사항을 반영하여야 함
- 여러 변경 사항은 하나에 Commit에 담는 것을 가급적 피할 것
- 수정, 변경, 업데이트는 구체적 변경사항 명시

## commit message 작성
- 50자 이내로 작성
- 대문자로 시작, 마침표는 사용하지 않음
- 현재형 동사 사용 – ADD, FIX, UPDATE
- 변경 사항의 요약 명확하게 작성

## 메세지 유형
- feat : 새로운 기능 추가
- perf : 성능 개선
- fix : 버그 수정
- docs : 문서 수정
- style : 코드 스타일 변경(포멧팅, 세미콜론 누락 등)
- refactor : 코드 리팩토링 (기능 변경 없이 코드 개선)
- test : 테스트 코드 추가 또는 수정
- clore : 빌드 관련 작업, 패키지 메니져 설정 등(코드 변경 없음)

```
feat: add user profile page
fix: resolve NPE in authentication service
docs: update README with installation steps
refactor: simplify user authentication logic
test: add unit tests for payment service
chore: update npm dependencies
```

[참고문헌](https://velog.io/@changonna/Git-Commit-Message-%EC%9E%91%EC%84%B1%EB%B2%95)