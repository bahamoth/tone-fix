# tone-fix

한국어 문서·인포그래픽·강의자료·슬라이드 덱의 AI 말투·번역체를 제거하고 명사구 제목·사실 기반 어조로 교정하는 Claude Code 플러그인.

## Installation

```bash
claude plugin marketplace add bahamoth/cc-marketplace
claude plugin install tone-fix
```

또는 이 레포를 직접 추가:

```bash
claude plugin add bahamoth/claude-tone-fix
```

## Usage

문서·덱·인포그래픽을 작성·마무리하는 단계에서 자동으로 활성화된다. 다음과 같은 요청으로도 트리거된다.

```
"이 문서 AI 말투 좀 고쳐줘"
"제목을 명사구로 바꿔줘"
"번역체 제거해줘"
"이 문장 AI스러운데 톤 다듬어줘"
```

## Features

- 운떼기 제목·수사의문문·상투어(`한눈에`, `살펴보기`, `정리하면`) 제거
- 1인칭·방어 톤·가정형·추측 단어 제거
- 미확정 구체(구현 방식·시점) 단정 금지
- 공간 채우기용 막연 문구·메타 노트 누출 제거
- 비전문가·구어체 어휘를 실무 전문가 어휘로 교정
- 한글 어절 단위 줄바꿈 규칙
- 마무리용 일괄 점검 grep 블록 제공 ([`skills/tone-fix/references/tone-rules.md`](skills/tone-fix/references/tone-rules.md))

## Configuration

별도 설정 불필요. 규칙은 [`skills/tone-fix/references/tone-rules.md`](skills/tone-fix/references/tone-rules.md) 에 내장되어 있다.
