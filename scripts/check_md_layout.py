#!/usr/bin/env python3
"""tone-fix 2b·3단계 MD 구조·가독성 검출기 (§10·§11).

용법:
    python3 scripts/check_md_layout.py <file.md>...

검출 항목
- §8.12 볼드 리드 프레임: 리드가 접속 부사(따라서·종합하면·즉·결국)로 시작하거나, 서술 포장(문제는 ~는 점이다)·자기지칭 예고(답하는 질문은 N가지다)·개수만 말하기(~는 세 가지다·~은 셋이다)로 끝남
- §8.12 두 절 리드: 볼드 리드 안에 연결 어미(-이고·-하고·-며·-지만·-어서·-므로·-면서·-는데)로 이어진 둘째 절이 있음
- §11.5 리드 뒤 부연: 마침표로 끝나는 볼드 리드와 같은 줄에 부연 텍스트가 이어짐 (`**라벨**:`·`**라벨**(…)` 형식은 제외)
- §8.12 형태 선택(수동 확인, `advisories:` 로 따로 집계): 리드가 `X 는 Y 이다 / 명사+다` 복사 구조이거나 `~가 명확하다·중요하다·크다` 같은 내용 없는 형용사 판정으로 끝남. 명사구로 바꿔 읽어 더 자연스러우면 명사구로, 내용이 비면 실제 내용으로 다시 쓴다. 유지하면 보고에 사유를 남긴다
- §10.1 요약 항목: 요약·TL;DR 절의 항목이 볼드 핵심 문장으로 시작하지 않거나, 핵심 문장이 60자를 넘거나, 항목이 3문장·200자를 넘음
- §10.2 문제제기 절: 요약 절이 있는 보고서형 문서에 개요·배경·문제·동기·현황·목적 계열 제목이 없음 (수동 확인)
- §10.3 단계 정의: `N단계` 를 쓰면서 그 단계를 정의하는 줄(표 행·목록·볼드 리드)이 없음. "6단계 구조" 같은 개수 표현은 제외
- §10.5 목록 도입 문장: 목록 바로 앞 문단이 개수 예고(`~은 셋이다`·`~는 세 가지다`·`~은 다음과 같다`)로 끝남. 명사구("노이즈의 세 가지 원인")로 바꾼다
- §11.1 키프레임: 제목·볼드·표·목록·코드 같은 시선 고정점 없이 본문이 900자 넘게 이어짐
- §11.2 문단 길이: 문단(목록 항목 포함)이 4문장 이상이거나 260자(공백 제외, 렌더 기준)를 넘음
- §11.3 볼드 남발: 한 문단에 볼드 구간이 3개 이상

마지막 두 줄 `advisories: N`(수동 확인, 사유 기록) 과 `violations: N`(0 이어야 통과). 코드 블록·표·HTML 블록은 검사에서 제외.
"""
import re
import sys

MAX_SENT = 3
MAX_CHARS = 260
SUMMARY_MAX_CHARS = 200
HOOK_MAX_CHARS = 60
ANCHOR_GAP = 900
MAX_BOLD = 2

HEAD = re.compile(r'^(#{1,6})\s+(.*)')
LIST = re.compile(r'^\s*([-*+]|\d+[.)])\s+')
TABLE = re.compile(r'^\s*\|')
FENCE = re.compile(r'^\s*(```|~~~)')
SUMMARY_HEAD = re.compile(r'^(요약|핵심 요약|한 줄 요약|TL;?DR|Summary|Executive Summary)\b', re.I)
MOTIVE_HEAD = re.compile(r'(개요|배경|문제|동기|현황|목적|배경과 문제|Overview|Background|Motivation|Problem)', re.I)
STAGE_USE = re.compile(r'(\d+)\s*단계(?!\s*(구조|체계|디렉터리|파이프라인|절차|과정|로 |의 |를 |으로|짜리))')  # "6단계 구조" 같은 개수 표현은 제외
STAGE_DEF = re.compile(r'^\s*(\|\s*|[-*+]\s+|\d+[.)]\s+)?\**\s*(\d+)\s*단계')
SENT_END = re.compile(r'''[가-힣%)\]'"’”」』a-zA-Z0-9]\.(\s|$)|[?!](\s|$)''')
BOLD = re.compile(r'\*\*[^*]+\*\*')
COPULA_LEAD = re.compile(r'(이다|[A-Za-z0-9)\]`%]다|(가지|갈래|항목|요소|건|개|종|축|단계|몫|담당|근거|원인|이유|핵심|답|해법|대안|전제|목표|조건|결과|함의|경계|차이|이점|가치|등가물|기준|원칙|정의|구조)다)\.?\s*\*\*$')
EMPTY_JUDGE = re.compile(r'(명확|분명|중요|필요|충분|핵심적|결정적|유효|타당|명백|확실)(하|이)다\.?\s*\*\*$|(크|작|많|적|낮|높)다\.?\s*\*\*$')
TWO_CLAUSE = re.compile(r'[가-힣A-Za-z0-9)]+(이고|하고|되고|있고|없고|내고|두고|쓰고|으며|며|지만|어서|아서|해서|므로|면서|는데)\s+\S')
SENT_LEAD = re.compile(r'^\*\*[^*]*[.!?]\s*\*\*|^\*\*[^*]+\*\*[.!?]')
LEAD_FRAME = [
    ('접속 부사 시작', re.compile(r'^\*\*\s*(따라서|종합하면|즉|결국|그래서|요컨대|정리하면)[,\s]')),
    ('서술 포장', re.compile(r'(는 점이다|다는 것이다|라는 것이다|라는 점이다|기 때문이다|는 데 있다)\.?\s*\*\*$')),
    ('자기지칭 예고', re.compile(r'(답하는|다루는|던지는|묻는) (질문|물음)|다음과 같(다|습니다)\.?\s*\*\*$')),
    ('개수만 말하기', re.compile(r'((한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|[0-9]+)\s*(가지|갈래|항목|종류|종|개|건)|(은|는|도) (하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열))(다|이다|입니다)\.?\s*\*\*$')),
]
# §10.5 목록 직전 문단이 개수 예고·자기지칭 예고로 끝남
COUNT_INTRO = re.compile(r'((은|는|도) (하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열)(이다|입니다)|(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|[0-9]+)\s*(가지|갈래|항목|종류|종|개|건|축|층|군|곳|단계)(다|이다|입니다|(가|이) 있다)|다음과 같(다|습니다))[.!:]?\s*$')


def strip_inline(t):
    t = t.replace('**', '')
    t = re.sub(r'`[^`]*`', ' ', t)
    t = re.sub(r'https?://\S+', ' ', t)
    t = re.sub(r'\([^)]*\)', ' ', t)          # 괄호 안 출처·보충은 문장 수에서 제외
    return t


def n_sent(t):
    return len(SENT_END.findall(strip_inline(t)))


def n_chars(t):
    # 렌더된 길이 기준: URL 만 제외하고 괄호·코드 내용은 그대로 센다
    t = re.sub(r'https?://\S+', ' ', t.replace('**', ''))
    return len(re.sub(r'\s+', '', t))


def check(path):
    lines = open(path, encoding='utf-8').read().split('\n')
    viol = 0
    adv = 0
    in_fence = False
    in_html = False
    section = ''
    in_summary = False
    heads = []
    stage_defs = set()
    stage_uses = {}
    gap = 0            # 마지막 시선 고정점 이후 누적 본문 글자 수
    gap_start = None
    para, para_start = [], None
    last_para = None   # 직전에 flush 된 문단 (§10.5 목록 도입 판정용)

    def flush():
        nonlocal viol, adv, para, para_start, last_para
        if not para:
            return
        text = ' '.join(l.strip() for l in para)
        is_list = bool(LIST.match(para[0]))
        last_para = (text, para_start, is_list)
        body_text = LIST.sub('', text, count=1) if is_list else text
        ns, nc = n_sent(body_text), n_chars(body_text)
        kind = '항목' if is_list else '문단'
        if in_summary:
            body = LIST.sub('', text, count=1)
            lead = BOLD.match(body)
            if not lead:
                viol += 1
                print(f'[§10.1 요약 {kind} L{para_start}] 볼드 핵심 문장으로 시작하지 않음: {text[:100]}')
            elif n_chars(lead.group(0)) > HOOK_MAX_CHARS:
                viol += 1
                print(f'[§10.1 요약 {kind} L{para_start}] 핵심 문장 {n_chars(lead.group(0))}자 (상한 {HOOK_MAX_CHARS}자): {lead.group(0)[:100]}')
            if ns > MAX_SENT or nc > SUMMARY_MAX_CHARS:
                viol += 1
                print(f'[§10.1 요약 {kind} L{para_start}] {ns}문장/{nc}자 (상한 {MAX_SENT}문장/{SUMMARY_MAX_CHARS}자): {text[:100]}')
        elif ns > MAX_SENT or nc > MAX_CHARS:
            viol += 1
            print(f'[§11.2 {kind} L{para_start}] {ns}문장/{nc}자 (상한 {MAX_SENT}문장/{MAX_CHARS}자): {text[:100]}')
        body0 = LIST.sub('', text, count=1)
        lead = BOLD.match(body0)
        if lead:
            first_line = LIST.sub('', para[0].strip(), count=1)
            tail = first_line[lead.end():].strip() if BOLD.match(first_line) else ''
            if SENT_LEAD.match(first_line) and re.sub(r'^[.!?)\s]+', '', tail):
                viol += 1
                print(f'[§11.5 리드 L{para_start}] 핵심 문장 뒤 같은 줄에 부연: {first_line[:100]}')
            if TWO_CLAUSE.search(lead.group(0)):
                viol += 1
                print(f'[§8.12 리드 L{para_start}] 두 절: {lead.group(0)[:100]}')
            for name, rx in LEAD_FRAME:
                if name == '개수만 말하기' and re.search(r'[·,:]', lead.group(0)):
                    continue                        # 내용을 나열한 뒤 개수를 말한 리드는 통과
                if rx.search(lead.group(0)):
                    viol += 1
                    print(f'[§8.12 리드 L{para_start}] {name}: {lead.group(0)[:100]}')
                    break
            else:
                if EMPTY_JUDGE.search(lead.group(0)):
                    adv += 1
                    print(f'[§8.12 리드 L{para_start}] (수동 확인) 내용 없는 형용사 판정: {lead.group(0)[:100]}')
                elif COPULA_LEAD.search(lead.group(0)):
                    adv += 1
                    print(f'[§8.12 리드 L{para_start}] (수동 확인) X는 Y다 복사 구조 → 명사구 검토: {lead.group(0)[:100]}')
        nb = len(BOLD.findall(re.sub(r'`[^`]*`', ' ', text)))   # 인라인 코드 안의 ** 는 제외
        if nb > MAX_BOLD:
            viol += 1
            print(f'[§11.3 {kind} L{para_start}] 볼드 {nb}개 (상한 {MAX_BOLD}): {text[:100]}')
        para, para_start = [], None

    if lines and lines[0].strip() == '---':          # YAML frontmatter 건너뛰기
        try:
            end = lines.index('---', 1)
            lines = [''] * (end + 1) + lines[end + 1:]
        except ValueError:
            pass
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip()
        if FENCE.match(line):
            flush()
            last_para = None
            in_fence = not in_fence
            gap, gap_start = 0, None
            continue
        if in_fence:
            continue
        if not in_html and re.match(r'^\s*<[a-zA-Z]', line):
            in_html = True
        if in_html:
            if not line.strip():
                in_html = False
            continue
        if not TABLE.match(line):                  # 표 셀·인라인 코드·따옴표 인용 안의 예시는 사용처로 세지 않음
            plain = re.sub(r'`[^`]*`|"[^"]*"|“[^”]*”', ' ', line)
            for m in STAGE_USE.finditer(plain):
                stage_uses.setdefault(m.group(1), i)
        dm = STAGE_DEF.match(line)
        if dm:
            stage_defs.add(dm.group(2))
        hm = HEAD.match(line)
        if hm:
            flush()
            last_para = None
            section = hm.group(2).strip().lstrip('0123456789. ')
            heads.append(section)
            in_summary = bool(SUMMARY_HEAD.match(section))
            gap, gap_start = 0, None
            continue
        if not line.strip():
            flush()
            continue
        if TABLE.match(line) or line.lstrip().startswith('>'):
            flush()
            last_para = None
            gap, gap_start = 0, None
            continue
        if LIST.match(line):
            flush()
            if last_para and not last_para[2]:
                intro = re.sub(r'\([^)]*\)', '', last_para[0].replace('**', '')).strip()
                if COUNT_INTRO.search(intro):
                    viol += 1
                    print(f'[§10.5 목록 도입 L{last_para[1]}] 개수 예고 문장으로 목록을 엶 → 명사구("노이즈의 세 가지 원인"): {last_para[0][:100]}')
            last_para = None
            gap, gap_start = 0, None
            para, para_start = [line], i
            continue
        if para and LIST.match(para[0]):
            para.append(line)              # 목록 항목의 이어지는 줄
            continue
        anchor = '**' in line
        if anchor:
            gap, gap_start = 0, None
        else:
            if gap_start is None:
                gap_start = i
            gap += n_chars(line)
            if gap > ANCHOR_GAP:
                viol += 1
                print(f'[§11.1 키프레임 L{gap_start}~{i}] 시선 고정점 없이 본문 {gap}자 이어짐 (상한 {ANCHOR_GAP}자)')
                gap, gap_start = 0, None
        if not para:
            para_start = i
        para.append(line)
    flush()

    has_summary = any(SUMMARY_HEAD.match(h) for h in heads)
    if has_summary and not any(MOTIVE_HEAD.search(h) for h in heads):   # 요약 절이 있는 보고서형 문서만
        viol += 1
        print(f'[§10.2 문제제기] 개요·배경·문제·동기 계열 절 제목이 없음 (수동 확인: 다른 이름으로 동기를 서술했으면 통과). 제목: {heads[:8]}')
    missing = sorted((s for s in stage_uses if s not in stage_defs), key=int)
    if len(stage_uses) >= 2 and missing:
        viol += len(missing)
        for s in missing:
            print(f'[§10.3 단계 정의 L{stage_uses[s]}] {s}단계 를 쓰지만 정의 줄(표 행·목록·볼드 리드가 "{s}단계" 로 시작)이 없음')
    return viol, adv


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    results = [check(p) for p in argv]
    total, adv = sum(r[0] for r in results), sum(r[1] for r in results)
    print('advisories:', adv)
    print('violations:', total)
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
