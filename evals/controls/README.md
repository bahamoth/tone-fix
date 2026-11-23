# 사람 글 대조군

규칙이 사람이 쓴 글을 위반으로 잡지 않는지 확인하는 글 묶음이다.
`evals/files/` 의 AI 초안 픽스처는 규칙이 잡아야 할 것을 확인하고, 이 디렉터리는 잡지 말아야 할 것을 확인한다.

```bash
python3 evals/harness/check_controls.py
```

`baseline.json` 에 없는 규칙이 걸리거나, 있는 규칙이 기준선보다 많이 걸리면 실패한다.
규칙이나 정규식을 고친 뒤에 돌린다.

## nars: 국회입법조사처 「이슈와 논점」 6편

| 파일 | 제목 | 작성자 | 호수, 발간일 | 원문 |
|---|---|---|---|---|
| `2015-06-29-wage-peak-system.md` | 임금피크제의 쟁점과 입법·정책적 시사점 | 김준 | 제1025호, 2015-06-29 | https://www.nars.go.kr/report/view.do?cmsCode=CM0018&brdSeq=16442 |
| `2016-03-18-ai-legislation.md` | 인공지능 기술발전과 입법정책적 대응방향 | 심우민 | 제1138호, 2016-03-18 | https://www.nars.go.kr/report/view.do?cmsCode=CM0018&brdSeq=18306 |
| `2017-03-02-village-education-community.md` | 마을교육공동체의 운영 현황 및 개선 과제 | 최지인 | 제1269호, 2017-03-02 | https://www.nars.go.kr/report/view.do?cmsCode=CM0018&brdSeq=20369 |
| `2018-03-26-us-steel-import-restriction.md` | 트럼프 행정부의 철강수입규제 조치와 한국의 대응방안 | 정민정 | 제1437호, 2018-03-26 | https://www.nars.go.kr/report/view.do?cmsCode=CM0018&brdSeq=22761 |
| `2019-08-12-heatwave-vulnerable-groups.md` | 폭염재난 취약계층 지원강화를 위한 개선과제 | 배재현, 김선화 | 제1602호, 2019-08-12 | https://www.nars.go.kr/report/view.do?cmsCode=CM0018&brdSeq=25708 |
| `2021-02-23-postal-voting.md` | 우편투표제도의 현황과 개선방안 | 김종갑 | 제1802호, 2021-02-23 | https://www.nars.go.kr/report/view.do?cmsCode=CM0018&brdSeq=33731 |

출처: 국회입법조사처(https://www.nars.go.kr) 「이슈와 논점」.
이용 조건: 공공누리 제1유형(출처표시). 각 보고서 상세 페이지의 공공누리 표시와 국회입법조사처 저작권정책(https://www.nars.go.kr/copyright.do)을 2026-11-18 에 확인했다.
이 디렉터리의 글에는 저장소의 MIT 라이선스 대신 위 이용 조건이 적용된다.

원문 PDF 에서 본문만 옮겼다.
머리말, 저자 소속 줄, 각주와 각주 번호, 표, 그림 설명, 조례 인용 상자, 판권은 뺐다.
큰 소제목은 `## `, 번호가 붙은 작은 소제목은 `### ` 로 적었다.
PDF 글자 매핑이 인쇄본과 달랐던 5곳(겹낫표 4곳, 소제목 '공동' 1곳)은 인쇄본대로 되돌렸다.
그 밖의 글자는 원문 그대로이고 문장을 고치지 않았다.

이 묶음을 고른 까닭은 문체다.
tone-fix 가 기준으로 삼는 글(실무자가 의사결정자에게 보내는 평어체 보고서)과 가장 가깝고, 모두 2022년 11월 이전에 사람이 썼다.
칼럼, 연설문, 수필은 1인칭과 수사의문문이 자연스러운 다른 문체라 이 점검에 넣지 않았다.
