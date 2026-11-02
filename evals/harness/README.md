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

채점기는 저장소의 `scripts/` 를 그대로 호출한다.
규칙을 바꾼 뒤 다시 채점하면 새 규칙이 반영된다.

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

## run 격리

`run_claude.sh` 는 `prompt.txt` 에 적힌 워크스페이스 경로를 저장소 밖 임시 디렉터리에 복사하고, 경로를 바꿔 그 안에서 실행한다.
끝나면 outputs 만 워크스페이스로 되가져오고 임시 디렉터리를 지운다.
그래서 run 세션은 저장소의 git 상태, evals.json 의 기대 결과, 최신 규칙을 볼 수 없다.

`prompt.txt` 에 워크스페이스 밖 저장소 경로가 남아 있으면 실행하지 않는다.
`evals/workspace/` 는 git 에서 제외되므로 `git clean -fdx` 를 실행하면 함께 지워진다.
