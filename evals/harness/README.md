# eval 하네스

스킬을 바꾸기 전과 후를 같은 eval 로 비교할 때 쓰는 실행기와 채점기.
run 산출물은 `evals/workspace/` 에 쌓이고 git 에서 제외된다.

## 파일

| 파일 | 하는 일 | 인자 |
|---|---|---|
| `run_claude.sh` | `prompt.txt` 로 `claude -p` 를 실행하고 `stream.jsonl`, `timing.json`, `done` 을 남긴다 | run 디렉터리 |
| `grade.py` | HTML eval 채점 (evals.json id 0~2) | run 디렉터리 |
| `grade_md.py` | MD 보고서 eval 채점 (id 3, harness-report) | run 디렉터리 |
| `grade_ctx.py` | 문맥 판독 eval 채점 (id 5, push-timing) | run 디렉터리 |
| `grade_tut.py` | 심은 표현 잔존과 수치 보존 집계 (id 7, tutorial-revamp) | 교정된 MD 파일 |
| `judge-prompt.md` | 블라인드 판정자 지시문 (id 6, roas-forecast) | 없음 |
| `check_controls.py` | 사람 글 대조군(`evals/controls/`)에서 `check_lexical.py` 히트가 기준선보다 늘었는지 점검 | 없음 (`--update` 로 기준선 갱신) |
| `review_ab.py` | 두 스킬의 교정본을 채점하고 원문과 줄 단위로 맞춘 대조 화면(`review.html`)을 만든다 | iteration 디렉터리 |

채점기는 저장소의 `scripts/` 를 그대로 호출한다.
규칙을 바꾼 뒤 다시 채점하면 새 규칙이 반영된다.

## eval 의 성격

`evals/files/` 의 픽스처는 회귀 시험이다.
픽스처에 심은 표현이 이미 규칙과 검출기에 들어가 있어, 통과해도 새 문서에서 잘 고친다는 뜻은 아니다.

규칙에 반영되지 않은 글로 보는 시험:

- **사람 글 대조군**(`evals/controls/`): 규칙이 사람이 쓴 보고서를 위반으로 잡지 않는지 본다. `python3 evals/harness/check_controls.py` 가 `failures: 0` 이어야 한다. 규칙이나 정규식을 고칠 때마다 돌린다.
- **전문가 교정 쌍**: 국립국어원 「한눈에 알아보는 공공언어 바로 쓰기」의 교정 사례는 이용 조건(공공누리 제4유형)에 따라 저장소에 넣지 않았다. `evals/workspace/control/nikl/` 에 두고 쓴다.

## 실행 순서

1. 비교할 스킬을 워크스페이스에 꺼낸다. 정답이 든 `evals/` 는 뺀다.

   ```bash
   cd evals/workspace && mkdir -p iteration-N/skill-old
   git archive <rev> | tar -x -C iteration-N/skill-old --exclude=evals
   rsync -a --exclude evals --exclude .git ../../ iteration-N/skill-new/
   ```

2. eval 디렉터리를 만든다.
   - 구성: `iteration-N/eval-K-이름/` 아래에 `inputs/`, `eval_metadata.json`, `with_skill/run-1/prompt.txt`, `with_skill/run-1/outputs/`
   - 대조군은 `with_skill` 대신 `old_skill` 아래에 같은 구성으로 둔다.
   - `eval_metadata.json` 에는 `eval_id`, `eval_name`, `prompt`, `assertions` 를 넣는다. `assertions` 는 evals.json 의 `expectations` 를 옮긴다.

3. `prompt.txt` 를 쓴다. 경로는 워크스페이스 절대 경로로 적는다.

   ```text
   Execute this task:
   - Skill path: <WS>/iteration-N/skill-new (read SKILL.md and follow it, including the files under references/ it points to, and run the scripts under scripts/ there). Use ONLY this skill directory. Do NOT invoke the installed tone-fix plugin skill via the Skill tool; it is a different version. Do not modify anything under the skill directory.
   - Task: <evals.json 의 prompt>
   - Input files: <WS>/iteration-N/eval-K-이름/inputs/<파일> (read-only; copy it into the outputs directory first and edit the copy)
   - Save outputs to: <WS>/iteration-N/eval-K-이름/with_skill/run-1/outputs/
   - Outputs to save: <파일> and report.md (every check command you ran, verbatim, with its final output, and the stage-by-stage list of edits you made). Create nothing outside that outputs directory.
   ```

4. 실행한다. 긴 문서는 15~40분 걸리므로 백그라운드로 돌린다.
   서브에이전트 판독이 필요하면 환경변수 `TOOLS=Bash,Read,Write,Edit,MultiEdit,Glob,Grep,Agent` 를 지정한다.

   ```bash
   # run 디렉터리는 evals/workspace 기준 상대 경로 또는 절대 경로
   evals/harness/run_claude.sh iteration-N/eval-K-이름/with_skill/run-1
   ```

5. 채점한다. 결과는 run 디렉터리의 `grading.json` 에 남는다.

   ```bash
   python3 evals/harness/grade.py evals/workspace/iteration-N/eval-K-이름/with_skill/run-1
   ```

## A/B 대조 화면

`review_ab.py` 는 iteration 디렉터리의 eval 마다 원문, 기존 스킬(`old_skill`) 교정본, 새 스킬(`with_skill`) 교정본을 읽는다.

```bash
python3 evals/harness/review_ab.py evals/workspace/iteration-N
open evals/workspace/iteration-N/review.html
```

- `eval_metadata.json` 에 `file`(대상 파일 이름)과 `kind`(문서 종류)가 있어야 한다.
- eval 디렉터리에 `reference/<파일>` 을 두면 사람이 승인한 교정본을 열 하나로 함께 보여 준다.
- 수치는 `grading.json` 에 남는다. 스캐너 위반, 레이아웃 위반, 수치 누락, 분량 변화, 바뀐 줄 수를 두 스킬에 같은 잣대로 잰다.
- 화면의 줄별 판정 버튼은 브라우저에만 저장된다. `내 판정 복사` 로 JSON 을 꺼낸다.
- eval 디렉터리에 `judge.json`(`overall`, `summary`, `count`, `items`, `info_loss`)을 두면 블라인드 판정을 참고 항목으로 함께 보여 준다.
- 화면의 줄별 판정은 브라우저에만 저장된다. '내 판정 복사' 로 받은 목록을 iteration 디렉터리의 `votes.json` 으로 저장하면 요약 표의 사람 판정 열에 실리고, 판정이 비어 있는 브라우저에서도 같은 판정이 채워진다.

HTML 은 화면에 보이는 글만, JSON 은 문자열 값만 대조한다.

## run 격리

`run_claude.sh` 는 `prompt.txt` 에 적힌 워크스페이스 경로를 저장소 밖 임시 디렉터리에 복사하고, 경로를 바꿔 그 안에서 실행한다.
끝나면 outputs 만 워크스페이스로 되가져오고 임시 디렉터리를 지운다.
그래서 run 세션은 저장소의 git 상태, evals.json 의 기대 결과, 최신 규칙을 볼 수 없다.

eval 디렉터리에 `project/` 가 있으면 그 내용을 run 의 작업 디렉터리 루트에 복사한다.
용어집을 적용한 run 을 보려면 `project/.tone-fix/glossary.md` 를 둔다. `prompt.txt` 에는 용어집을 적지 않는다.

`prompt.txt` 에 워크스페이스 밖 저장소 경로가 남아 있으면 실행하지 않는다.
`evals/workspace/` 는 git 에서 제외되므로 `git clean -fdx` 를 실행하면 함께 지워진다.
