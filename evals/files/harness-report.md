# 모델에 종속되지 않는 에이전트 하베스(harness) 설계: Orca 위 Claude Fable 5.1 & GPT-6 Astra 워크플로우 아키텍처

## TL;DR
- **모델별 지시문(prompt)을 계속 다시 쓰는 문제는 "6계층 분리 + 모델 어댑터 계층 격리"로 구조적으로 해결할 수 있다.** 벤더 문서가 이를 직접 뒷받침한다: Anthropic은 `/claude-api migrate`, OpenAI는 `$openai-docs migrate`로 모델 종속적 변경을 자동화하고, 두 벤더 모두 "설정 파일(CLAUDE.md/AGENTS.md/skills)을 감사(audit)하라"고 명시한다. 즉 워크플로우 구조(L0~L3, L5)는 모델 무관하게 유지하고, 모델 종속 nudge는 L4 어댑터 파일 한 곳에만 모아 vendor migrate 스킬로 재생성하는 것이 정답이다.
- **교차 벤더 검증(Claude가 구현→Astra가 리뷰, 또는 반대)은 동일 모델 자기 리뷰보다 더 많은 결함을 잡는다는 증거가 실무·연구 양쪽에서 수렴한다.** 같은 모델 계열은 상관된 맹점(correlated blind spots)을 공유하므로, Orca의 Run/Task/Dispatch/worker/gate 위에 "reviewer는 read-only, writer는 worktree를 받는" 역할 분리를 얹는 것이 권장된다(Orca 공식 사이트 인용 사용자 포스트: "Reviewers read only; writers get worktrees").
- **하베스 설정 자체를 CI에서 회귀 테스트(eval)하는 것이 새 모델 온보딩의 핵심**이다. `claude -p --output-format json --allowedTools`와 Codex 비대화형 모드로 20~50개 실제 작업 eval을 돌리되, Orca 오케스트레이션은 experimental이고 기본적으로 권한 우회 플래그를 켜므로 이를 설계에서 반드시 감안해야 한다.

## Key Findings

1. **Orca 오케스트레이션은 experimental이며 "레거시 명령이 은퇴"했다.** `orca orchestration run`/`run-stop`/`coordinator-start`/`coordinator-stop`은 아무 효과가 없고(no effects), 복구 텍스트로 `orca skills get orchestration --full`을 가리킨다. 실제 흐름은 `run-create → task-create → worker-start → check --wait → send --type worker_done`이다. 플래그는 앱 버전에 따라 바뀌므로 `orca skills get orchestration --full`이 유일한 진실 소스(source of truth)다. (출처: https://www.onorca.dev/docs/cli/orchestration)

2. **Orca는 모든 지원 에이전트를 "완전 자율" 권한 우회 플래그로 미리 채워서(pre-fill) 실행한다.** Claude는 `--dangerously-skip-permissions`, Codex는 `--dangerously-bypass-approvals-and-sandbox`, Gemini/Cursor 등은 `--yolo`. 근거는 "worktree는 일회용(disposable)"이라는 것. 중간 권한 모드(Claude Auto, Codex "Approve for me")는 아직 선택 불가(이슈 #13081). 이는 L3 hook/gate 설계에 직접 영향을 준다. (출처: https://www.onorca.dev/docs/agents/supported , https://github.com/stablyai/orca/issues/13081)

3. **두 벤더의 모델별 프롬프팅 가이드는 정반대 방향으로 nudge를 요구한다** — 이것이 어댑터 계층을 분리해야 하는 핵심 이유다. Fable 5.1은 anti-formatting 규칙 제거, "hold findings" 라인 제거, effort 재측정, "user is not watching" 자율성 블록, append-only history를 요구한다. GPT-6 Astra는 bias-to-action, "concrete reviewable result만 승인", user-instructions-over-skills 우선순위, 일시정지 유발 SKILL.md 지목 프롬프트를 요구한다.

4. **migrate 스킬이 바꾸는 것과 사람에게 남기는 것의 경계가 명확하다.** Anthropic `/claude-api migrate`는 모델 ID 스왑, 파괴적 파라미터 변경, prefill 교체, effort 보정, Bedrock/AWS ID 포맷 조정을 자동 수행하고 편집 전 범위를 확인받으며, 완료 시 수동 검증 체크리스트(통합 테스트, length-control 프롬프트 튜닝, 비용/rate-limit 재산정)를 생성한다. OpenAI `$openai-docs migrate`는 모델 문자열과 직접 관련된 프롬프트만 좁게 바꾸고, 과거 문서·eval 베이스라인·SDK/auth/tooling 마이그레이션은 명시 요청 없이는 손대지 않는다.

5. **교차 모델 리뷰의 이점은 실무 보고와 연구에서 모두 확인된다.** 같은 모델이 코드를 쓰고 리뷰하면 상관된 맹점을 재생산한다. Augment Code는 Codex reviewer가 Claude 계열이 놓친 버그를 찾아 실제 CVE를 산출한 libfuse 캠페인을 보고했다(아래 상세 인용).

## Details

### 1. 크로스 벤더 오케스트레이션 하베스 비교 — 역할 간 안정적 계약(contract)이 어디에 사는가

**Orca (onorca.dev)** — Orca는 "ADE(Agent Development Environment)"로, 25개 이상의 CLI 에이전트(Claude Code, Codex, OpenCode, Cursor CLI, Grok, Gemini, GitHub Copilot, Pi 등)를 각자 격리된 git worktree에서 병렬 실행한다. 공식 사이트(onorca.dev)는 "Run Claude Code, Codex, Gemini, Cursor CLI, and every other CLI agent in parallel across isolated worktrees"로 소개한다. Orca는 Stably AI(YC 지원 4인 팀, San Francisco)의 MIT 라이선스 Electron 앱이며, AgentConn(2026) 보도에 따르면 첫 커밋 5개월 만에 GitHub 53,000 스타를 돌파했다. 오케스트레이션 계층의 핵심 원시(primitive)는 문서에 명확히 정의되어 있다(출처: https://www.onorca.dev/docs/cli/orchestration):
- **Run** — durable namespace이자 coordinator inbox. 워커를 스케줄하거나 배치하지 않음.
- **Task** — spec, 의존성, 상태(`pending`/`ready`/`dispatched`/`completed`/`failed`/`blocked`)를 가진 작업 항목.
- **Dispatch** — 한 터미널에서의 task 1회 시도. `worker_done`/heartbeat의 라이프사이클 권한을 가짐.
- **Message** — inbox 메일(`status`, `dispatch`, `worker_done`, `escalation`, `question`, `heartbeat`).
- **Decision gate** — coordinator 소유 질문으로 task를 blocking.

**안정적 계약(stable contract):** 워커 완료·heartbeat 메시지는 반드시 `taskId`와 `dispatchId`를 모두 포함해야 하며(오래된 워커가 최신 작업을 완료 처리하는 것 방지), `worker_done`은 정확히 한 번, `--outcome succeeded|failed`와 함께 보내야 한다. 완료 권한(completion authority)은 활성 dispatch 컨텍스트에서 나온다. 이는 supervisor/executor 역할 사이의 "메시지 타입 + 필수 ID + outcome" 계약이다. 역할 분리 원칙도 공식 사이트에 인용된 사용자 포스트가 압축한다: "Orca tracks CLI agents' worktrees, tasks, and completion. One clear goal per worker. Reviewers read only; writers get worktrees. Run in parallel, wait for worker_done. One owner integrates and tests."

Orca는 per-worker 모델/effort 오버라이드도 지원한다: `worker-start --agent claude --model <opaque-model-id> --effort high` (Claude, Codex, Cursor만; `--terminal`과 병용 불가). 이는 교차 벤더 검증(한 워커는 claude, 다른 워커는 codex)을 CLI 한 줄로 구성 가능하게 한다.

**Claude Code** — 계약은 파일과 exit code로 표현된다. `CLAUDE.md`(항상 로드되는 프로젝트 컨텍스트, 3계층 병합: enterprise/user/project), `.claude/agents/*.md`(subagent, frontmatter로 `tools`/`disallowedTools`/`model`/`permissionMode`/`memory`/`effort`/`isolation` 지정), `.claude/skills/*/SKILL.md`(on-demand, progressive disclosure), `settings.json`(hooks/permissions). Hook은 exit code 2로 차단(block)하며, PreToolUse/PostToolUse/Stop/SubagentStop/TaskCreated/TaskCompleted 등 라이프사이클 이벤트에 걸린다. 역할 분리 원칙: **CLAUDE.md는 규약, skill은 정책 조언, hook은 절대 안 되는 것을 차단** — 이는 결정론적 계층(hook)과 확률적 계층(skill/CLAUDE.md)의 명확한 분리다. (출처: https://code.claude.com/docs/en/sub-agents , https://code.claude.com/docs/en/permission-modes)

**OpenAI Codex** — 계약은 `AGENTS.md`(작업 디렉터리에서 루트까지 walk-up하며 모든 AGENTS.md 로드), `.codex/agents/<role>.md`, `config.toml`의 `[agents]` 섹션(`max_threads` 기본 6, `max_depth` 기본 1, `job_max_runtime_seconds`)으로 표현된다. 중요: **reviewer 역할은 `sandbox_mode = "read-only"`로 명시 설정**하는 것이 권장된다(리뷰어는 절대 쓰면 안 됨). Responses API의 멀티에이전트 모드는 `/root` 루트와 `/root/researcher` 같은 계층적 경로 주소를 쓰며, `max_concurrent_subagents` 기본값 3, 6개의 hosted collaboration action을 제공한다. Astra 신기능: async tool calling(`async: true`), mid-turn steering(WebSocket으로 완료 작업 보존), `configuration_update`로 캐시 보존하며 effort 변경. (출처: https://developers.openai.com/api/docs/guides/responses-multi-agent , https://developers.openai.com/api/docs/guides/latest-model)

**에이전트 무관(agent-agnostic) 오픈소스 하베스:**
- **Hermes Agent (NousResearch)** — provider-agnostic. 모델·프로바이더를 워크플로우 중간에 스왑, credential pool 자동 로테이션. 명시적으로 "generic framework는 planner/executor 추상화로 시작하지만 Hermes는 실제 운영 표면(CLI, 파일, 도구, 메모리, 스킬, cron, 메시징 게이트웨이)에서 시작"이라고 대비시킨다. build+review 패턴(한 에이전트 구현, 다른 에이전트가 diff 감사)을 권장하며 **"워커 자기 보고를 검증 없이 신뢰하지 말라 — 경로/URL/테스트 출력/스크린샷 등 구체적 handle을 요구하고 orchestrator가 확인하라"**를 hard invariant로 둔다. (출처: https://hermes-agent.ai/blog/hermes-agent-multi-agent)
- **OpenCode** — Orca가 그룹 주소(`@opencode`)로 1급 지원하는 오픈소스 에이전트.
- 학술 프레임워크(VERIMAP arXiv 2510.17109, BMW Agents arXiv 2406.20041, ChatMotion 등)는 planner→executor→verifier 역할을 DAG로 정형화하며, 특히 verifier가 "plan이나 부분 결과에 대한 지식 없이" 검증하여 편향을 방지하는 패턴을 공통적으로 채택한다.

**모델별 nudge가 사는 곳:** 세 하베스 모두에서 모델 종속 행동 조정은 (a) 시스템 프롬프트/AGENTS.md/CLAUDE.md, (b) skill 파일에 흩어져 산다. 이것이 문제의 근원이며, 해결책은 이를 단일 어댑터 파일(L4)로 격리하는 것이다.

### 2. 모델 어댑터 패턴 — migrate 스킬이 실제로 바꾸는 것

**Anthropic `/claude-api migrate`** (출처: https://platform.claude.com/docs/en/models/fable-5-1/migration-guide 및 Claude API skill 문서 https://platform.claude.com/docs/en/agents-and-tools/agent-skills/claude-api-skill). 마이그레이션 가이드는 다음과 같이 명시한다: "The skill applies the model ID swap and, as needed, breaking parameter changes, prefill replacement, and effort calibration for your target model across your code base, then produces a checklist of items to verify manually. It asks you to confirm the migration scope (entire working directory, a subdirectory, or a specific file list) before editing any files. The skill also detects Amazon Bedrock and Claude Platform on AWS clients and adjusts model ID formats and feature changes for those platforms."

Claude API skill 문서의 상세 목록에 따르면 스킬이 자동 처리하는 것: 모델 ID 스왑(타입드 SDK 상수 포함, 파일을 caller/model definer/opaque string으로 분류), 클라우드 플랫폼 감지(Bedrock의 `anthropic.` prefix 보존), 파괴적 파라미터 변경, prefill을 structured output으로 변환, beta 헤더 정리, effort 보정, 프롬프트 동작 튜닝 플래깅, refusal fallback 설정(`stop_reason: "refusal"` 처리 추가). **사람에게 남기는 것**: "On completion, it produces a checklist of items that require manual verification (typically integration tests, length-control prompt tuning, and cost/rate-limit re-baselining)." 범위가 모호하면(예: 맨 `/claude-api migrate to claude-opus-5`) 스킬은 편집 전에 "entire working directory / specific subdirectory / explicit file list" 중 선택을 요구한다.

**OpenAI `$openai-docs migrate`** (출처: https://developers.openai.com/api/docs/guides/latest-model). 자동/체크 항목: `model`을 `gpt-6-astra`로; reasoning effort가 `none`/`minimal`이면 `low`로 시작(그 외에는 기존 유효 effort 보존); `temperature`/`top_p`/`top_logprobs` 제거(Chat Completions는 `logprobs`도, Responses는 `include`에서 `message.output_text.logprobs`도); tool calling은 Responses API 필요; `prompt_cache_retention`을 `prompt_cache_options.ttl: "30m"`로 교체(GPT-5.5 이하에서 마이그레이션 시). **사람에게 남기는 것**: SKILL.md(github.com/openai/skills/.curated/openai-docs)가 경계를 정한다 — "keep changes narrow: update active OpenAI API model defaults and directly related prompts only when safe" 그리고 "Leave historical docs, examples, eval baselines, fixtures, provider comparisons, provider registries, pricing tables, alias defaults, low-cost fallback paths, and ambiguous older model usage unchanged unless the user explicitly asks to upgrade them", "Keep SDK, tooling, IDE, plugin, shell, auth, and provider-environment migrations out of a model-and-prompt upgrade unless the user explicitly asks for them", "If an upgrade needs API-surface changes, schema rewiring, tool-handler changes, or implementation work beyond a literal model-string replacement and prompt edits, report it as blocked or confirmation-needed."

**핵심 함의:** 두 migrate 스킬 모두 (1) 모델 문자열/파라미터/effort 같은 기계적 변경은 자동화하지만, (2) **프롬프트 행동 튜닝과 eval 검증은 명시적으로 사람에게 남긴다.** 따라서 "모델별 nudge"는 자동 생성될 수 없는 판단 영역이며, 이를 L4 어댑터 파일에 모아두면 migrate 스킬이 그 파일 하나를 재생성 대상으로 삼을 수 있다.

**커뮤니티 실무 (Eric Provencher, OpenAI Codex DX, 2026-09-05 "Rethinking skills and prompts for GPT-6 Astra"):** recipe식(itinerary-style) 스킬은 이제 신모델을 과잉 제약한다. skill root는 supporting docs/scripts를 가리키는 **minimal router**여야 하며 progressive disclosure가 유용한 스킬의 표식이다. 결정적으로 **"Guidance that helps Sol or Luna may overconstrain GPT-6 Astra, so consider which models will use the instructions you leave behind"** — 즉 레포 스킬은 서로 다른 모델을 쓰는 기여자의 에이전트도 안내하므로 모델 무관하게 써야 한다. 이것이 어댑터 분리의 커뮤니티 측 근거다. (출처: https://x.com/pvncher/status/2095991462416490862)

### 3. Verifier/critic 역할 설계

**Playbook의 4가지 관련 lesson (academy.claude.com/courses/ai-native-sdlc-playbook):**
- **"Give Claude a feedback loop"**: 검증을 hook으로 강제 — task를 done으로 보고하기 전 검증, 수정 중 테스트 파일 편집 차단. 증거는 툴체인에서 나온 literal 출력(`make test`, 빌드 로그, 스크린샷 diff)이며 세션 transcript와 PR check run에 기록된다. 버그 수정은 실패하는 테스트를 먼저 커밋하고, 테스트를 편집하지 않고 통과시키게 한다. 선행 지표는 "agent-written 변경의 first-pass CI success rate". (출처: https://academy.claude.com/courses/ai-native-sdlc-playbook/give-claude-a-feedback-loop)
- **"Parallel sessions and subagents"**: 각 병렬 task는 자체 worktree. subagent 예시로 **verifier(앱을 실행하고 동작 확인), code simplifier, researcher**를 `.claude/agents/`에 markdown으로 정의하고 git에 체크인. 2~3 세션에서 시작, 리뷰가 따라가는 한에서만 추가. (출처: https://claude.com/blog/the-ai-native-sdlc-playbook)
- **"AI in the PR review loop"** + **"Hooks as approval gates"**: gate가 먼저 존재해야 자동화가 그것을 통과시킨다. read-only 판단 스텝(`claude -p`로 빌드 실패 triage)에서 시작, write 스텝은 기존 gate 뒤에 배치. 에이전트가 쓰는 것은 모두 branch protection을 통해 PR로 도착하고 main에 직접 push할 경로가 없다. (출처: https://academy.claude.com/courses/ai-native-sdlc-playbook/ci-cd-integration-and-deployment)

**구조화된 verdict artifact:** Codex reviewer 패턴은 구조화된 JSON(severity level 포함)을 산출하도록 권장된다. 커뮤니티(sdlc.xeb.ai의 Playbook 정리)는 "test/feature manifest를 append-only 정책으로 — 에이전트(와 사람)는 pass/fail을 뒤집을 뿐 기준을 삭제하지 않는다"와 "모든 'done' 주장은 첨부된 검증 artifact(통과한 테스트 실행, 스크린샷, eval 점수)를 요구"를 강조한다.

**교차 벤더 검증이 더 잡는가 — 증거:**
- **실무(자기 보고):** Augment Code의 'Adversarial Code Review' 가이드는 다음과 같이 명시한다(verbatim): "In the libfuse campaign, a Codex agent found bugs that Claude-family review missed and identified correctness issues in proposed fixes that additional Claude-family agents did not catch. The campaign produced published CVEs. Same-family loops can leak because models from the same family share correlated blind spots and often end up confidently agreeing in the same places." 개별 개발자 실무 보고도 이를 반영한다 — Todd Orr("What I Found When Claude Reviewed Codex's Work", Medium): "I run two coding agents day to day. Claude Code is my primary. OpenAI Codex is my reviewer... Codex routinely flags Critical-tier issues that Claude missed reviewing its own work, and Claude tends to agree once the issue is surfaced." 동일 모델 자기 리뷰는 "The implementation looks correct. Tests cover the main paths" 식의 피상적 결과를 내는 경향이 있다.
- **연구:** arXiv 2607.21656("Cross-Model LLM Code Review")은 same-model self-repair가 자기 코드에 대한 유용한 피드백 능력에 병목되어 modest한 개선만 낸다는 기존 발견을 재현하되, "high reasoning effort에서 Claude Opus 4.7은 static reviewer가 찾을 오류를 이미 대부분 잡아 second pass에 신호가 적다"는 뉘앙스도 제시한다. arXiv 2604.19049(Refute-or-Promote)는 "Cross-Model Critic(CMC): 다른 모델 계열 에이전트가 최소 컨텍스트로 독립 비평 — same-family 리뷰가 놓치는 상관된 training-data 오류를 잡는다"를 정형화한다.
- **종합 판단:** 교차 벤더 검증은 상관된 맹점이 문제인 고위험 경로(권한 변경, 인증 플로우, 대형 agent-authored diff)에서 특히 가치가 크다. 다만 신모델일수록 자기 검증이 강해져 이득이 줄 수 있으므로, 비용 대비 효과를 eval로 측정해 고위험 경로에 우선 적용하라.

### 4. 하베스 설정용 eval 스위트

**비대화형 실행 메커니즘 (Claude Code):** `claude -p`가 print/headless 모드. 핵심 사실 — **`-p`는 hooks/skills/plugins/MCP/CLAUDE.md의 auto-discovery를 건너뛴다**(더 빠른 시작; Claude Academy "Routines and headless" 명시). `--bare`는 이 모든 ambient discovery를 완전히 생략하는 결정론적(deterministic) 모드로 CI 재현성에 적합. `--output-format json`은 `total_cost_usd`, `session_id`, `is_error`, `num_turns`를 반환하고 `--json-schema`로 structured output을 강제(구조화된 부분은 `structured_output` 필드에 안착). 스킬 활성화만 테스트하려면 `--output-format stream-json --verbose --max-turns 1 --allowedTools Skill`로 tool_use 이벤트를 파싱(Scott Spence의 sandboxed eval 사례, 22 test case × 5 config 총 $5.59). **함의:** CLAUDE.md/skills/hooks를 회귀 테스트하려면 `-p`가 이들을 건너뛴다는 점 때문에, eval은 이들을 명시적으로 로드하는 full-context `-p` 실행으로 돌려야 하고, `--bare`는 "clean room" 대조군으로 쓴다. (출처: https://academy.claude.com/courses/claude-code-in-action/routines-and-headless , https://scottspence.com/posts/measuring-claude-code-skill-activation-with-sandboxed-evals)

**Codex 등가물:** `codex exec`(비대화형), `.curated`의 skill을 통한 CI 실행, `config.toml`로 sandbox/approval 스코프.

**20~50 real-task eval 구조화 (커뮤니티·연구 수렴):** Playbook은 "20~50개 real task로 eval을 추가하고 plan-to-diff 체크를 git hook으로 강제"를 권한다. 각 task는 지시를 올바로 따르는 에이전트가 풀 수 있어야 하고(모호한 spec으로 실패하면 안 됨), grader가 확인하는 모든 것은 task 설명에서 명확해야 한다. balanced problem set(행동이 일어나야 할 때 AND 일어나면 안 될 때 모두 테스트)이 one-sided 최적화를 방지. deterministic grader(tool call 검증, argument 검증, outcome 검증, transcript 분석)를 우선.

**eval이 판별력을 잃을 때(saturation) 처리:** 연구·실무 공통 지침 — eval 스위트가 100%면 개선 신호가 없다. saturation에 근접하면 큰 능력 향상도 작은 점수 증가로 보여 점수가 기만적이 된다. 대응: **capability eval(낮은 pass rate, hill-climbing용)이 성숙하면 regression eval(near-100% 유지, backslide 방지 guardrail)로 승격**하고, 기존 스위트가 포화되기 *전에* 더 어려운 eval을 도입. 프로덕션 실패를 새 test case로, contamination 모니터링으로 item 은퇴, score 분포로 판별력 상실 감지. 포화된 벤치마크도 accuracy 외 차원(효율, 신뢰성, 토큰/tool call 수)에서는 여전히 유용(CORE-Bench 사례, arXiv 2606.26158).

### 5. 이 사용자를 위한 구체적 권장 레이아웃

Orca는 레포별로 `.claude/`와 `.codex/`를 읽고 `CLAUDE.md`/`AGENTS.md`는 그대로 둔다는 전제 하에, 6계층(L0~L5) 디렉터리 구조를 제안한다.

```
repo/
  intent/                         # L0: intent.md → spec.md → plan.md (Playbook 아티팩트 체인)
    2026-09-09-feature-x.intent.md
    2026-09-09-feature-x.spec.md
    2026-09-09-feature-x.plan.md
  CLAUDE.md                       # L1: 프로젝트 사실/규약 (1페이지 이내, 항상 로드)
  AGENTS.md                       # L1: Codex용 동일 사실 (walk-up 로드)
  .claude/
    settings.json                 # L3: hooks/permissions (결정론적 gate)
    skills/                       # L2: minimal router SKILL.md + progressive disclosure
      <domain>/SKILL.md
    agents/                       # L2/역할: verifier.md, planner.md, executor.md
      verifier.md                 #   tools: Read,Bash(test only); permissionMode 제한
    adapters/                     # L4: 모델 종속 계층 (유일한 모델 의존 파일)
      fable-5-1.md
      _shared.md
    hooks/                        # L3: 차단 스크립트 (exit code 2)
  .codex/
    agents/
      code-reviewer.md            #   sandbox_mode = "read-only"
    adapters/
      gpt-6-astra.md              # L4
  evals/                          # L5: 20~50 real-task eval + grader
    cases/
    run.sh                        # claude -p / codex exec 비대화형 러너
```

**L1 CLAUDE.md/AGENTS.md 원칙:** 항상 로드되는 규약만. Anthropic 권장은 CLAUDE.md를 ~1페이지로 유지하고 상세는 디렉터리별 규칙이나 skill로. 모델 종속 nudge를 여기 넣지 말 것(이것이 재작성 지옥의 원인).

**L4 어댑터 템플릿 — Fable 5.1 vs GPT-6 Astra 대조 (어떤 nudge가 어디로 가는가):**

| 행동 축 | `.claude/adapters/fable-5-1.md` | `.codex/adapters/gpt-6-astra.md` |
|---|---|---|
| Formatting | anti-formatting 규칙 **제거**; "필요할 때만 리스트" 규칙으로 대체 (5.1은 오히려 bold/헤더를 덜 씀) | "clear, concise paragraphs 기본; 진짜 병렬/순차일 때만 리스트" (Astra는 리스트/테이블 과다) |
| Task 완료 | "user is not watching" 자율성 블록 + scope 블록 추가; "hold findings for final response" 라인 제거 | bias-to-action 프롬프트("can you...", "I want to..."를 실행 지시로 취급); "concrete reviewable result만 승인" |
| Effort | 전 레벨 재측정(default high; medium이 Fable 5의 high 근접); 이름이 같아도 사고량 다름 | `none`/`minimal` 사용 중이면 `low`부터; 나머지는 유효 effort 보존 |
| Tool 배칭 | agent loop에서 batch-tool-call nudge 추가 | async tool calling 활용; subagent 위임을 명시적으로 지시(Astra는 위임을 덜 함) |
| History | **append-only** (thinking block이 정확한 대화에 바인딩; prefix 변경 시 400) | mid-turn steering(WebSocket) 활용 |
| Skill 충돌 | (해당 없음) | "user instructions > skills" 우선순위 명시 + 일시정지 유발 SKILL.md 지목 디버그 프롬프트 |
| 편집 | targeted-edit nudge(전체 파일 재작성 방지) | 작은 변경에 over-test 억제 프롬프트 |
| Subagent | lead agent가 subagent 대기 중에도 계속 작업 | 언제/얼마나 위임할지 명시 |

각 어댑터 파일 상단에 모델 ID와 재생성 커맨드를 주석으로: `<!-- regenerate: /claude-api migrate this project to claude-fable-5-1 -->`, `<!-- regenerate: $openai-docs migrate this project to GPT-6 Astra -->`.

**Orca 오케스트레이션 레시피 — supervised plan → execute → verify → gate (교차 벤더 verifier):**

먼저 `orca skills get orchestration --full`로 현재 플래그를 확인(진실 소스)하고 Settings → Experimental에서 오케스트레이션을 켠 뒤 `orca status --json`이 성공하는지 확인. 그다음:

```bash
# 0) 진실 소스 확인 (플래그가 앱 버전에 따라 변함)
orca skills get orchestration --full

# 1) Run 생성 (durable namespace + coordinator inbox)
orca orchestration run-create --objective "Feature X: plan→execute→cross-verify→gate" --json

# 2) Task 생성 (execute, verify) — spec에 의존성 기술
orca orchestration task-create --spec "spec.md/plan.md로부터 구현" --task-title "Execute" --json
orca orchestration task-create --spec "교차 벤더 검증: 구현 diff를 read-only로 리뷰, JSON verdict 산출" --task-title "Verify" --json

# 3) Executor 워커 (Claude Fable 5.1, worktree new-child)
orca orchestration worker-start --task <execTaskId> --worktree new-child \
  --name feat-x-exec --agent claude --model <fable-5-1-id> --effort high --setup run --json

# 4) Verifier 워커 (교차 벤더: Codex/GPT-6 Astra) — 다른 worktree, reviewer는 read-only 지향
orca orchestration worker-start --task <verifyTaskId> --worktree current \
  --agent codex --json

# 5) coordinator는 완료 대기 (poll 금지, worker_done/escalation/question 대기)
orca orchestration check --wait --types worker_done,escalation,question --timeout-ms 900000 --json

# 6) decision gate: 검증 통과 시에만 병합 진행
orca orchestration gate-create --task <execTaskId> \
  --question "Verifier가 clean verdict를 냈는가? 병합 진행?" --options '["yes","no"]' --json
orca orchestration gate-resolve --id <gateId> --resolution "yes" --json
```

워커(executor)는 완료 시 `orca orchestration send --type worker_done --task-id <t> --dispatch-id <d> --outcome succeeded --files-modified "..." --json`으로 보고. verifier는 blocking 질문이 있으면 `orca orchestration ask`를 쓰고 결과를 `jq -r .answer`로 파이프. 역할 매핑: **supervisor=coordinator(Run), planner/executor/verifier=worker(Task+Dispatch), 승인=decision gate.** reviewer worktree는 read-only 의도로 쓰되, Orca가 권한 우회 플래그를 pre-fill하므로 진짜 read-only 강제는 Codex `sandbox_mode="read-only"` 에이전트 파일이나 Claude subagent의 `disallowedTools`로 L3에서 별도 보장해야 한다.

**새 모델 온보딩 체크리스트 (repeatable):**
1. `orca skills get orchestration --full`로 현재 CLI 플래그 재확인(experimental이라 변동).
2. 벤더 migrate 스킬 실행: `/claude-api migrate ... to <new-model>` 또는 `$openai-docs migrate ... to <new-model>`. 편집 범위 확인 프롬프트에 응답.
3. migrate가 생성한 **수동 검증 체크리스트** 처리(통합 테스트, length-control 프롬프트 튜닝, 비용/rate-limit 재산정).
4. L4 어댑터 파일만 갱신(새 모델의 프롬프팅 가이드 diff 반영). L0~L3, L5는 건드리지 않음.
5. effort 레벨 재측정(이름이 같아도 사고량 다름) — 대표 task로 low/medium/high/xhigh 스윕.
6. L5 eval 스위트를 신·구 모델 양쪽에 실행: `evals/run.sh`가 `claude -p --output-format json`(+full-context로 CLAUDE.md/skills 로드)과 `--bare` 대조군을 돌리고 `total_cost_usd`·pass rate 비교.
7. skill 감사: 두 벤더 모두 명시 권고. recipe식 과잉 제약 skill을 minimal router로 축소, 신모델을 과잉 제약하는 라인 제거.
8. eval saturation 점검: 신모델이 전부 통과하면 더 어려운 case 추가; 포화된 case는 regression guardrail로 승격.
9. 교차 벤더 verifier 설정 확인: 새 모델이 executor면 verifier는 다른 벤더로.

## Recommendations

**즉시 (이번 주):**
- L4 어댑터 계층을 지금 만들어라. `.claude/adapters/fable-5-1.md`와 `.codex/adapters/gpt-6-astra.md`를 위 대조표대로 작성하고, CLAUDE.md/AGENTS.md/skills에 흩어진 모델 종속 nudge를 전부 이 파일들로 이관하라. 각 파일 상단에 재생성 커맨드를 주석으로 박아라.
- CLAUDE.md/AGENTS.md를 ~1페이지 규약으로 다이어트하고, 모델 종속 문장을 0으로 만들어라.
- skill root를 minimal router로 리팩터(progressive disclosure). Provencher의 경고대로 recipe식 라인을 제거하라.

**단기 (2~4주):**
- L5 eval을 구축하라: 최근 버그·리뷰 코멘트에서 20~50개 real task를 뽑아 deterministic grader와 함께 `evals/run.sh`에 넣고, `claude -p --output-format json`(full-context)와 `--bare` 대조로 돌려 CI에 건다. **트리거: CLAUDE.md/skills/hooks 변경 또는 모델 스왑 시 자동 실행**(Playbook 원칙).
- L3 hook/gate를 세워라: "task done 보고 전 검증 통과"와 "수정 중 테스트 파일 편집 차단"을 hook(exit code 2)으로. Orca가 권한 우회를 pre-fill하므로, 이 결정론적 gate가 유일한 실질 안전 경계다.
- 고위험 경로(권한 변경·인증·대형 diff)부터 교차 벤더 verifier를 켜라. Orca `worker-start`로 executor=Claude, verifier=Codex(read-only sandbox) 구성.

**중기 (분기):**
- 새 모델 온보딩 체크리스트를 조직 slash command/skill로 codify. Playbook의 "product owner가 intent.md 승인 → 비대화형 job이 트리거" 패턴을 차용.
- eval saturation을 모니터링하고 capability→regression 승격 파이프라인을 운영.

**결정을 바꾸는 임계치(benchmark/threshold):**
- 교차 벤더 verifier의 **추가 결함 검출률이 추가 토큰·지연 비용을 정당화하지 못하면**(예: 신모델 자기검증이 강해져 second-pass 신호가 미미) 고위험 경로로만 축소하라(arXiv 2607.21656의 뉘앙스).
- eval **first-pass CI success rate**가 목표치(예: 저위험 변경에서 반복적으로 통과)에 도달하면 해당 변경 클래스의 auto-accept를 확대하라(Playbook 선행 지표).
- **정책 관련 리뷰 코멘트가 0에 수렴하지 않으면** skill이 발화하지 않거나 실제 정책과 문구가 어긋난 것이니 skill을 수정하라(Playbook 자체 측정 기준).

## Caveats

- **Orca 오케스트레이션은 experimental이고 플래그가 자주 바뀐다.** 이 보고서의 CLI 시퀀스는 2026-09-09 기준 문서(https://www.onorca.dev/docs/cli/orchestration) 스냅샷이다. 실제 실행 전 반드시 `orca skills get orchestration --full`로 현재 플래그를 확인하라 — 문서가 명시적으로 이를 유일한 진실 소스로 지정한다. `orca orchestration run`류 레거시 명령은 이미 은퇴하여 no-effect다.
- **Orca의 권한 우회 pre-fill은 설계의 전제이자 위험이다.** 중간 권한 모드는 아직 미지원(이슈 #13081). 관련 취약점 CVE-2026-33068(GitHub Advisory GHSA-mmgp-wc2j-qcv7, 2026-03-19 공개; CVSS v4.0 7.7 HIGH; CWE-807)은 "Versions prior to 2.1.53 resolved the permission mode from settings files, including the repo-controlled .claude/settings.json, before determining whether to display the workspace trust confirmation dialog. A malicious repository could set permissions.defaultMode to bypassPermissions... causing the trust dialog to be silently skipped on first open"로, 패치 버전은 2.1.53이다. 신뢰되지 않은 레포에서는 컨테이너 격리와 L3 hook을 반드시 병행하라.
- **모델 이름·날짜의 검증 한계:** Claude Fable 5.1(2026-09-01)·GPT-6 Astra(2026-09-03~04)의 출시일과 프롬프팅 가이드 내용은 벤더 문서에서 확인된 사실이다. 그러나 "교차 벤더 검증이 더 잡는다"는 일부 근거(Augment Code의 libfuse CVE 사례, Todd Orr의 개인 실무 보고 등)는 벤더/업체·개인 블로그의 자기 보고이며 독립 재현이 제한적이다. arXiv 논문들은 다양한 모델 세대(일부는 GPT-4/Code Llama)를 대상으로 하므로 Fable 5.1/Astra 세대에 그대로 일반화되지 않을 수 있다.
- **migrate 스킬의 상세 목록 일부**(예: `temperature`/`top_p`/`top_k` 제거는 Opus 4.8/4.7 타깃 예시)는 소스·타깃 모델 조합에 따라 실제 편집이 달라진다. Fable 5.1 경로의 구체적 breaking change는 forced `tool_choice`가 400을 반환하는 것 등이다. 반드시 자신의 코드베이스에서 migrate 실행 후 생성된 체크리스트를 검증하라.
- **벤더-문서 사실 / 커뮤니티 실무 / 본 보고서 합성 권장의 구분:** 1~4절의 벤더 문서 인용(Orca docs, platform.claude.com, developers.openai.com, academy.claude.com)은 1차 사실이다. Provencher의 글, Augment/MindStudio/WorkOS/Todd Orr 블로그, Codex Knowledge Base는 커뮤니티 실무다. 5절의 디렉터리 구조·어댑터 대조표·Orca 레시피·온보딩 체크리스트는 이들 사실을 종합한 본 보고서의 권장안이며, 실제 환경에서 eval로 검증되어야 한다.
