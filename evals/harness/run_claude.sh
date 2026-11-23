#!/bin/bash
# usage: run_claude.sh <run_dir>   — claude -p 실행, stream.jsonl 저장, 종료 시 timing.json + done 마커
# run_dir 은 evals/workspace 기준 상대 경로 또는 절대 경로.
# run 은 저장소 밖 임시 디렉터리에서 돈다. prompt.txt 에 적힌 워크스페이스 경로(스킬 스냅숏, 입력, outputs)를
# 그쪽에 복사하고 경로를 바꿔 실행한 뒤 outputs 만 되가져온다. 저장소의 git 상태, evals.json, 최신 규칙을 run 이 보지 못하게 한다.
WS="$(cd "$(dirname "$0")/../workspace" && pwd)"; REPO="$(dirname "$(dirname "$WS")")"; cd "$WS"
RUN="$(cd "$1" && pwd)" || exit 2
TMP="$(mktemp -d "${TMPDIR:-/tmp}/tone-fix-eval.XXXXXX")"; PF="$(mktemp "${TMPDIR:-/tmp}/tone-fix-prompt.XXXXXX")"
python3 - "$WS" "$TMP" "$RUN" "$REPO" > "$PF" <<'PY' || { rm -rf "$TMP" "$PF"; exit 2; }
import pathlib, re, shutil, sys
ws, tmp, run, repo = sys.argv[1:]
prompt = (pathlib.Path(run) / 'prompt.txt').read_text()
for p in sorted(set(re.findall(re.escape(ws) + r'/[^\s()\'"]*', prompt))):
    src = pathlib.Path(p.rstrip('.,;:'))
    dst = pathlib.Path(tmp) / src.relative_to(ws)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    elif src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    else:
        dst.mkdir(parents=True, exist_ok=True)
prompt = prompt.replace(ws, tmp)
if repo in prompt:
    sys.exit(f'prompt.txt 가 워크스페이스 밖 저장소 경로를 가리킨다: {repo}')
print(prompt, end='')
PY
PROMPT="$(cat "$PF")"; rm -f "$PF"
# eval 디렉터리(run_dir 의 두 단계 위)에 project/ 가 있으면 작업 디렉터리 루트에 깐다(예: project/.tone-fix/glossary.md)
EV="$(dirname "$(dirname "$RUN")")"; [ -d "$EV/project" ] && cp -R "$EV/project/." "$TMP/"
cd "$TMP"
env -u CLAUDECODE claude -p "$PROMPT" \
  --output-format stream-json --verbose \
  --permission-mode acceptEdits \
  --allowedTools "${TOOLS:-Bash,Read,Write,Edit,MultiEdit,Glob,Grep}" \
  > "$RUN/stream.jsonl" 2> "$RUN/stderr.log"
RC=$?
OUT="$TMP/${RUN#$WS/}/outputs"
[ -d "$OUT" ] && mkdir -p "$RUN/outputs" && cp -R "$OUT/." "$RUN/outputs/"
cd "$WS" && rm -rf "$TMP"
python3 - "$RUN" <<'PY'
import json, sys, pathlib
run = pathlib.Path(sys.argv[1]); res = None
for line in (run/'stream.jsonl').read_text().splitlines():
    try: ev = json.loads(line)
    except Exception: continue
    if ev.get('type') == 'result': res = ev
if res:
    u = res.get('usage', {}) or {}
    tot = sum(u.get(k, 0) for k in ('input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens'))
    ms = res.get('duration_ms', 0)
    (run/'timing.json').write_text(json.dumps({'total_tokens': tot, 'duration_ms': ms, 'total_duration_seconds': round(ms/1000, 1),
        'num_turns': res.get('num_turns'), 'is_error': res.get('is_error'), 'subtype': res.get('subtype')}, indent=2))
    print('timing written', tot, ms)
else:
    print('no result event')
PY
echo $RC > "$RUN/done"
