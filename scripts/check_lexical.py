#!/usr/bin/env python3
"""tone-fix 1단계 결정론적 점검 — 어휘·패턴 스캐너.

용법:
    python3 scripts/check_lexical.py [--honorific] [--glossary <용어집> | --no-glossary] <file>...

- 규칙표(references/tone-rules.md)의 어휘 신호를 정규식으로 잡는다. 의존성 없음.
- 마지막 줄 `hits: N` 이 0 이어야 1단계 통과. 예외가 있는 규칙(수동 확인 표시)은
  판단 후 그대로 둘 수 있으나, 보고에 사유를 남긴다.
- 규칙 끝에 "title" 이 붙은 규칙은 제목, 라벨 줄에서만 검사한다. 본문의 '살펴보면',
  '~겠는가.' 는 사람이 쓴 보고서와 칼럼에도 흔해 본문에서는 잡지 않는다.
- 정규식을 고친 뒤에는 `python3 evals/harness/check_controls.py` 를 돌려
  사람이 쓴 보고서(evals/controls/)에서 히트가 늘지 않았는지 확인한다.
- `--honorific`: §6 존대 문서(의사결정자 대상)에서만 켠다. 평어체 잔존을 추가로 잡는다.
- 용어집(§8.16): 프로젝트 루트의 `.tone-fix/glossary.md` 가 있으면 읽어 '쓰지 않는 표기' 를 위반으로 센다.
  형식은 `| 쓰지 않는 표기 | 쓰는 표기 | 비고 |` 표. 읽었으면 첫 줄에 `glossary: <경로>` 를 찍는다.
  현재 디렉터리, 다음으로 검사할 파일의 디렉터리에서 git 저장소 루트까지만 올라가며 찾는다.
  저장소가 아니면 그 디렉터리만 본다.
  홈 디렉터리, 스킬 디렉터리, 환경변수는 보지 않는다.
- `--glossary <파일>`: 그 파일을 용어집으로 쓴다(프로젝트 용어집 대신). `--no-glossary`: 용어집 없이 돌린다.
"""
import os
import re
import sys

GLOSSARY_REL = os.path.join(".tone-fix", "glossary.md")

# (규칙, 설명, 정규식, 수동확인 여부[, "title"])
RULES = [
    ("§2", "1인칭·친근 표현 (의사결정자 대상 보고 기준. 칼럼, 연설문, 블로그처럼 필자가 드러나는 글이면 유지)",
     r"저희|우리 측|우리가|여러분|에게 —", True),
    ("§3·§4", "일정 가정형·추측 표현 (소스 인용이면 유지. 근거 있는 분석 서술 '발생할 가능성이 높다' 는 대상 아님)",
     r"만약|슬립|지연됩니다|늦어(지|집|질)|(지연|차질|연기|순연|밀리|밀릴)[^.\n]{0,12}(가능성|수 있|우려)"
     r"|예상 ?(슬립|지연)|(예상|추정)(한다|합니다|된다|됩니다)", True),
    ("§5", "메타 보일러플레이트 라벨 (발신, 수신, 기준일, 다음 보고. 본문 낱말 '수신자', '발신하는' 은 대상 아님)",
     r"(?:^|[\s>|*(\-])(발신|수신|기준일|다음 보고)(?:자|인|처)?\**\s*(?:[:：|]|</)|(?:기준일|다음 보고)\s*[0-9]", True),
    ("§8", "상투 도입어", r"한눈에|쉽게 말해|정리하면", False),
    ("§8", "AI 상투 제목·수사의문문 신호 (제목, 라벨 줄만)",
     r"살펴보|알아보|무엇을 [^.?\n]{0,30}(하나|할까|예측)|왜 [^.?\n]{0,30}(인가|있나|나뉘)|어떻게 [^.?\n]{0,30}(하나|할까|보)", False, "title"),
    ("§8", "수사의문문 어미로 끝나는 제목·라벨 (제목, 라벨 줄만)",
     r"(인가|한가|는가|을까|일까|할까|있나|없나|나요)\.?(<|·| ·| —|:|\*|\"|\s*$)", False, "title"),
    ("§8·§8.1", "자기지칭 메타 라벨·수사적 3연 나열·빈 프레이밍",
     r"이 (덱|문서|장표|페이지|자료)(의)?\s*(구성|목적|내용|개요)|어떤 [^.?\n]{0,30}(거치|하며)|무엇을 [^.?\n]{0,30}(하며|하는가|보게|연동)|인지로 본다|로 본다 —|를 (살펴본다|알아본다)", False),
    ("§8.2", "메타 노트 누출·중언부언",
     r"\((모듈별|예시로|여기에|참고(?!로)|작성자|내부용|TODO)|반복한다\.|이를 통해|되는 셈", False),
    ("§8.2", "'~하면 된다' 군더더기 (절차나 해법을 지시하는 문장이면 유지)", r"하면 (된다|됩니다)\.", True),
    ("§8.3", "제목 수량 꼬리표", r"s-title[^<]*[0-9]+(종|개|가지)", False),
    ("§8.3", "뜻이 넓은 동사 (실제 동작이 수집, 연동, 노출, 활성화면 그 동사로. 받기만 하는 동작이면 유지)",
     r"(?<![가-힣])(받는다|붙인다|띄운다|켠다|받습니다|붙입니다|띄웁니다|켭니다)\.|다르게 대한", True),
    ("§8.2", "공간 채우기용 막연 문구", r"그 외 [^.\n]{0,30}도 |기타 (다양|여러)|등등|필요 시 [^.\n]{0,20}맞게|상황에 맞게", False),
    ("§8.4", "미확정 구체 단정 신호 (소스에 있으면 유지)",
     r"내장\(embedded\)|곧 (출시|지원)|다음 (분기|버전|업데이트).*지원|자동으로 (처리|동작)", True),
    ("§8.6", "대시(— –) 전면 금지 (제목 구분자 포함. 영어 인용문 안만 예외)", r"[—–]", False),
    ("§8.15", "가운뎃점(·) 금지 (나열은 쉼표, 꼬리는 쉼표·괄호. 요일 축약 토·일 만 예외. 변형 ‧ ㆍ ・ 포함)", r"[·‧ㆍ・]", False),
    ("§8.2", "문서 내부 참조 안내문 (이 표의 이름을 쓴다 / 아래 절에서 다룬다)",
     r"(이|위|아래|다음|본|해당) ?(표|절|목록|장|문단)(의|은|는|이|가|에서)? ?[^.\n]{0,25}(지칭|참조|참고|쓴다|씁니다|사용한다|다룬다|다룹니다|설명한다|정의한 대로)|[0-9]+절(의|이|가) [^.\n]{0,30}(쓴다|씁니다|참조|사용)", True),
    ("§8", "관형절 + 추상명사 번역투 제목 (결정을 바꾸는 임계치)",
     r"(바꾸는|가르는|좌우하는|유발하는|결정짓는|이끄는) (임계치|임계값|기준|조건|지표|요인|변수)", True),
    ("§8.8", "fire 번역투 '발화' (파생형 포함)", r"발화", False),
    ("§8.9", "대조 강조 구문 'A 가 아니라 B 다' (역할 구분 정보면 두 단정문으로)", r"(이|가|은|는) 아니라", True),
    ("§8.1", "부제 술부 문장 (HTML s-sub/d-sub)",
     r'class="(s-sub|d-sub)[^"]*"[^>]*>[^<]*(한다|된다|있다|없다|이다|아니다|다)\.<', False),
    ("§8.10", "계층 코드 라벨 L0~L5 (업계 표준 용어면 유지)",
     r"\bL[0-9]\s*[~–-]\s*L?[0-9]\b|\bL[0-9] ?(계층|레이어|어댑터|단계)|[0-9] ?계층\s*\(L[0-9]", True),
    ("§8.12", "핵심 문장 서술 포장 '문제는 ~는 점이다 / ~는 것이다' (제목, 요약 훅, 볼드 리드, 절 첫 문장만. 본문 서술이면 유지)",
     r"(문제|핵심|요점|결론|이유|함의|관건|포인트|차이|답)(은|는) [^.\n]{0,60}(는 점이다|다는 것이다|라는 것이다|라는 점이다|기 때문이다|는 데 있다)", True),
    ("§8.12", "자기지칭 예고 '이 문서가 답하는 질문은 N 가지다 / ~은 다음과 같다'",
     r"(문서|보고서|글|절|장|자료)(가|이) (답하는|다루는|던지는|묻는|제기하는) (질문|물음)|(질문|물음)(은|는) [^.\n]{0,6}가지|(은|는) 다음과 같(다|습니다)", True),
    ("§8.12", "개수 예고 문장 '~은 셋이다 / ~는 세 가지다' (목록 도입이면 명사구 '노이즈의 세 가지 원인' 으로, 목록 없는 사실 수치면 유지)",
     r"(은|는|도) ((하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열)(이다|입니다)|(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|[0-9]+) ?(가지|갈래|항목|종류|종|개|건|축|층|군|곳|단계)(다|이다|입니다|(가|이) 있다))[.!]?(\s|$|<)", True),
    ("§8.16", "굳은 외래어 용어의 직역 (noise→소음, source→원천, horizon→지평, endpoint→종단점, handler→처리기. 물리적 소음·원천징수 등 본뜻이면 유지)",
     r"소음|잡음|원천(?!적|징수)|지평(?!선)|종단점|(?<!전)처리기|청취자|되부름|적재물|깔때기|동질 집단|음소거", True),
    ("§8.13", "사람 동사 직역 (retired→은퇴, kill→죽이다, graceful→우아한, alive→살아 있다)",
     r"은퇴|우아하(게|ㄴ)|우아한|(프로세스|명령|작업|워커|세션|스레드|서비스|커넥션)[을를]? ?죽|(워커|프로세스|세션|서비스|커넥션)(가|이) 살아|(기능|명령|API|서비스)(이|가) (태어|죽)", True),
    ("§8.11", "문서 자기지칭 의인화 '이 문서는 ~에 답한다'",
     r"(문서|보고서|글|자료|장|절)(는|은|가|이) [^.\n]{0,60}(답한다|답합니다|다룬다|다룹니다|제안한다|제안합니다|보여준다|보여줍니다|주장한다|주장합니다|살펴본다|묻는다|묻습니다)", False),
    ("§8.14", "'더' + 동작 동사 직결 (더 잡는다 → 더 많이/잘 잡는다. '2주 더 관찰한다' 처럼 수량이 앞에 있으면 대상 아님)",
     r"(?<![가-힣])더 (?!많이|잘|적게|자주|빨리|늦게|오래|크게|작게|높게|낮게|넓게|깊게|쉽게|어렵게|있|없)[가-힣]{0,4}(는다|한다|낸다|든다|쓴다|둔다|본다|준다|긴다|친다|린다|킨다|인다|운다|(?:잡|찾|받|먹|읽|막|얻|넣|놓|쌓|뽑|담|남)습니다)(\.|,|\s|$)", False),
    ("§8.3", "구어 '갈아 끼우다' (→ 교체·변경)", r"갈아 ?끼", False),
    ("§8.11", "추상명사 의인화 '근거가 수렴한다'",
     r"(근거|증거|결론|의견|보고|연구|사례|데이터|결과)[^.\n]{0,40}(수렴|한곳으로 모|한 방향|가리킨다|가리킵니다|향한다|향합니다|말해 준다|말해 줍니다|말한다|말합니다|이야기한다|이야기합니다)", True),
    ("§12.11", "어울리지 않는 서술어 '판단이 나온다' (판단은 내리다, 하다)", r"판단(이|은|도) (나온|나오|나왔|나옴)", False),
    ("§12.11", "수치 비교에 '갈린다' (갈리다는 의견, 판단에 쓴다. 수치는 '차이가 크다')",
     r"(%|%p|배|명|건|원)\)?[^.\n]{0,20}(으?로) 갈(린다|렸다|리는|린|립니다)", True),
    ("§12.10", "보고서에 쓰지 않는 구어 (머릿속 → 기준으로 삼은, 출렁임 → 변동, 따라왔다 → 근접했다)",
     r"머릿속|출렁|따라왔|따라온다", True),
    ("§8.17", "비유 '축' (두 축, 세 축으로, 한 축, 주축, 속도 축과 비용 축 → 근거, 기준, 원칙 같은 실제 이름을 쓰거나 항목을 바로 나열. 그래프 x축, 가로축, 회전축은 제외)",
     r"(?:(?<=[\s0-9(\[|\"'“‘/])|^|(?<=주)|(?<=양)|(?<=중심)|(?<=핵심)|(?<=비교)|(?<=평가)|(?<=분석)|(?<=성장)|(?<=전략)|(?<=판단)|(?<=행동))축(?=[은는이가을를과와도의에로별만,.;:)\]|/·\s\"'”’]|으로|입니다|$)", False),
]
HONORIFIC_RULES = [
    ("§6", "평어체 잔존 (존대 문서만)", r"(이다\.|한다\.|된다\.)", False),
]


WEEKDAY = re.compile(r"[월화수목금토일]([·‧ㆍ・][월화수목금토일])+")
# §8.14 예외: 수량 + 더 ('2주 더 관찰한다', '1,925명이 더 남는다'). 수량이 '더' 의 정도를 이미 말한다
QUANT_MORE = re.compile(r"[0-9][0-9,.]*\s?[가-힣%p]{0,3}(이|가|을|를|씩|만|은|는)? ?더 ")
# §8.17 예외: 그래프, 좌표, 기계의 실제 축
REAL_AXIS = re.compile(r"[xyzXYZ] ?축|(가로|세로|좌표|회전|대칭|수평|수직|보조|지구|자전) ?축|[0-9]+ ?축 ?(센서|가속도|자이로|짐벌|로봇|모터|가공|스테이지)")
SKIP = {"§8.15": WEEKDAY, "§8.17": REAL_AXIS, "§8.14": QUANT_MORE}   # 예외 표기를 지운 뒤 검사

# 제목, 라벨 줄: MD 제목, 볼드만 있는 줄, HTML 제목 계열 태그와 클래스, JS 의 title 류 키
TITLE_MARK = re.compile(
    r"^\s*#{1,6}\s"
    r"|^\s*(?:[-*]\s+|[0-9]+\.\s+)?\*\*[^*]+\*\*[:：]?\s*$"
    r"|<(?:h[1-6]|title|th|dt|summary|caption|figcaption|label|button)\b"
    r"|class=\"[^\"]*(?:title|sub|label|head|eyebrow|kicker|caption|chip|badge)"
    r"|\b(?:title|subtitle|label|heading|name)\s*:\s*[\"'`]"
)
MARKUP = re.compile(r"<[^>]+>|[*_`#>|]|^\s*(?:[-+]|[0-9]+\.)\s+")


def is_title_line(ln):
    """제목, 라벨 줄인가. 표지가 없어도 마침표 없이 30자 이내로 끝나는 줄은 라벨로 본다."""
    if TITLE_MARK.search(ln):
        return True
    text = MARKUP.sub("", ln).strip()
    return 0 < len(text) <= 30 and not re.search(r"[.!]\s*$", text)


def read_lines(path):
    """파일을 줄 목록으로 읽는다. 코드 블록 안은 검사하지 않으므로 빈 줄로 바꾼다."""
    with open(path, encoding="utf-8") as fh:
        raw = fh.read().split("\n")
    lines, fence = [], False
    for ln in raw:
        if ln.lstrip().startswith(("```", "~~~")):
            fence = not fence
            lines.append("")
            continue
        lines.append("" if fence else ln)
    return lines


def find(path, rules):
    """규칙마다 (규칙, 설명, 수동확인, [(줄 번호, 줄, 매치)]) 를 낸다. 히트가 없는 규칙은 건너뛴다."""
    lines = read_lines(path)
    for rule, desc, pat, manual, *scope in rules:
        rx = re.compile(pat)
        skip = SKIP.get(rule)
        found = []
        for i, ln in enumerate(lines):
            if scope and not is_title_line(ln):
                continue
            m = rx.search(skip.sub("", ln) if skip else ln)
            if m:
                found.append((i + 1, ln, m))
        if found:
            yield rule, desc, manual, found


def project_glossary(starts):
    """프로젝트 루트의 .tone-fix/glossary.md 경로를 돌려준다. 없으면 None.

    starts 의 각 디렉터리에서 git 저장소 루트(.git 이 있는 디렉터리)까지 올라가며 보고, 먼저 나온 것을 쓴다.
    저장소가 아니면 그 디렉터리만 본다. 저장소 밖과 홈 디렉터리로는 올라가지 않는다.
    """
    for start in starts:
        here = os.path.abspath(start)
        chain, d = [here], here
        while not os.path.exists(os.path.join(d, ".git")):
            parent = os.path.dirname(d)
            if parent == d:                         # 저장소가 아니다
                chain = [here]
                break
            d = parent
            chain.append(d)
        for d in chain:
            p = os.path.join(d, GLOSSARY_REL)
            if os.path.isfile(p):
                return os.path.relpath(p)
    return None


def load_glossary(path):
    """용어집 표를 [(쓰지 않는 표기, 쓰는 표기, 줄 번호)] 로 읽는다.

    쓰지 않는 표기가 빈 행은 고정 표기(그대로 두는 말)다. 검사 대상은 아니지만 교정자가 읽으므로 함께 돌려준다.
    """
    with open(path, encoding="utf-8") as fh:
        raw = fh.read().split("\n")
    rows = []
    for n, ln in enumerate(raw, 1):
        if not ln.lstrip().startswith("|"):
            continue
        cells = [c.strip().strip("`").strip() for c in ln.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):   # 구분선: 바로 앞 행이 머리글
            if rows:
                rows.pop()
            continue
        if len(cells) >= 2 and cells[1]:
            rows.append((cells[0], cells[1], n))
    return rows


def find_glossary(path, entries):
    """용어집의 쓰지 않는 표기를 찾는다. find 와 같은 꼴로 낸다. 띄어쓰기 차이(구멍 게임, 구멍게임)는 같은 표기로 본다."""
    lines = read_lines(path)
    for ban, pref, n in entries:
        if not ban:
            continue
        rx = re.compile(r"\s*".join(re.escape(w) for w in ban.split()), re.I)
        mask = bool(rx.search(pref))                # 쓰는 표기가 쓰지 않는 표기를 품으면(홀 → 홀 게임) 쓰는 표기는 지우고 검사
        found = []
        for i, ln in enumerate(lines):
            m = rx.search(ln.replace(pref, "\0" * len(pref)) if mask else ln)
            if m:
                m = rx.match(ln, m.start())         # 지우지 않은 줄에서 같은 자리를 다시 잡아 문맥을 보인다
                found.append((i + 1, ln, m))
        if found:
            yield "용어집", f"'{ban}' → '{pref}' (용어집 {n}행)", False, found


def scan(path, rules, glossary=()):
    hits = 0
    for rule, desc, manual, found in list(find(path, rules)) + list(find_glossary(path, glossary)):
        tag = " (수동 확인)" if manual else ""
        print(f"## {rule} {desc}{tag}")
        for n, ln, m in found:
            hit = m.group(0)
            if len(hit) < 3:                        # 한두 글자 매치(축, ·)는 앞뒤 문맥을 함께 보인다
                hit = m.string[max(0, m.start() - 8):m.end() + 4].strip()
            print(f"  {path}:{n}: {ln.strip()[:120]}  ← {hit!r}")
        hits += len(found)
    return hits


def main(argv):
    honorific = "--honorific" in argv
    files, gpath, no_glossary, it = [], None, False, iter(argv)
    for a in it:
        if a == "--glossary":
            gpath = next(it, None)
            if not gpath:
                print("--glossary 뒤에 용어집 파일 경로가 없다")
                return 2
        elif a.startswith("--glossary="):
            gpath = a.split("=", 1)[1]
        elif a == "--no-glossary":
            no_glossary = True
        elif not a.startswith("--"):
            files.append(a)
    if not files:
        print(__doc__)
        return 2
    glossary = []
    if no_glossary:
        gpath = None
    elif not gpath:
        gpath = project_glossary([os.getcwd()] + [os.path.dirname(os.path.abspath(f)) for f in files])
    if gpath:
        try:
            glossary = load_glossary(gpath)
        except OSError as e:
            print(f"용어집을 읽지 못했다: {gpath} ({e.strerror})")
            return 2
        banned = sum(1 for b, _, _ in glossary if b)
        print(f"glossary: {gpath} (쓰지 않는 표기 {banned}, 고정 표기 {len(glossary) - banned})")
    rules = RULES + (HONORIFIC_RULES if honorific else [])
    total = sum(scan(f, rules, glossary) for f in files)
    print(f"hits: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
