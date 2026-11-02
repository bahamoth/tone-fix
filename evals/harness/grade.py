"""HTML eval 채점: python3 grade.py <run_dir> (eval 0 l1-workbench, 1 liveops-report, 2 threshold-panel). 스킬 저장소의 scripts/ 를 그대로 쓴다.

원본은 2026-10-30 워크스페이스 삭제로 사라져 2026-11-02 evals.json 단언과 픽스처로 다시 만들었다. 단언 순서는 evals.json expectations 와 같다.
본문과 인라인 JS 문자열을 <br>, 블록 태그 기준 렌더링 줄로 나눠 명사구 꼬리 처리와 문장 경계 <br> 를 본다.
"""
import html, itertools, json, re, subprocess, sys, pathlib
from collections import Counter

run = pathlib.Path(sys.argv[1]).resolve()
eval_dir = run.parent.parent
meta = json.loads((eval_dir / 'eval_metadata.json').read_text())
EID = meta['eval_id']
REPO = pathlib.Path(__file__).resolve().parents[2]
SK = REPO / 'scripts'
A = meta.get('assertions') or next(e['expectations'] for e in json.loads((REPO / 'evals/evals.json').read_text())['evals'] if e['id'] == EID)
out = run / 'outputs'
srcs = sorted((eval_dir / 'inputs').glob('*.html'))
src = srcs[0].read_text(encoding='utf-8') if srcs else ''
m = re.search(r'파일명은 (\S+?\.html)', meta.get('prompt', ''))
html_path = out / (srcs[0].name if srcs else m.group(1) if m else '_')
if not html_path.exists():
    found = sorted(out.glob('*.html'))
    html_path = found[0] if len(found) == 1 else html_path
doc = html_path.read_text(encoding='utf-8') if html_path.exists() else ''
report = (out / 'report.md').read_text(encoding='utf-8') if (out / 'report.md').exists() else ''

BLOCK = r'</?(?:p|div|dd|dt|dl|li|ul|ol|h[1-6]|section|article|header|footer|main|small|table|tr|td|th|figure|figcaption|blockquote)\b[^>]*>'
STR = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`')   # check_br.py 와 같은 JS 문자열
_blk = itertools.count()


def frag_lines(frag, where):
    res, blk, br = [], next(_blk), False
    for part in re.split(rf'(<br\s*/?>|{BLOCK})', frag):
        if re.fullmatch(r'<br\s*/?>', part):
            br = True
        elif re.fullmatch(BLOCK, part):
            blk, br = next(_blk), False
        else:
            t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', part)).replace('\\n', ' ')).strip()
            if t:
                res.append({'text': t, 'br': br, 'blk': blk, 'where': where})
                br = False
    return res


def doc_lines(s):
    """렌더링 줄 목록. text, br(<br> 바로 뒤), blk(블록 번호), where(html/js), unit(같은 블록 전체 텍스트)."""
    b = re.search(r'<body\b[^>]*>(.*)</body>', s, re.S)
    body = b.group(1) if b else s
    scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', body, re.S)
    ls = frag_lines(re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', body, flags=re.S), 'html')
    for sc in scripts:
        for sm in STR.finditer(sc):
            ls += frag_lines(sm.group(0)[1:-1], 'js')
    for l in ls:
        l['unit'] = ' '.join(x['text'] for x in ls if x['blk'] == l['blk'])
    return ls


ls = doc_lines(doc)
vis = '\n'.join(l['text'] for l in ls)


def run_script(name):
    if not doc: return '', '산출물 없음'
    r = subprocess.run([sys.executable, str(SK / name), str(html_path)], capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    return (lines[-1] if lines else ''), r.stdout.strip()


def tails(*specs):
    """명사구 꼬리가 <br> 뒤 단독 줄이나 마침표 뒤 조각으로 남지 않고 쉼표, 괄호로 앞 문장에 붙었는지. spec = (꼬리, 찾을 토큰, 위치)."""
    ok, ev = True, []
    for phrase, key, where in specs:
        cands = [l for l in ls if key in l['text'] and (not where or l['where'] == where)]
        if not cands:
            ok = False; ev.append(f'{phrase}: 찾지 못함'); continue
        for l in cands:
            t = l['text']
            d = re.findall(r',|\(|\.(?=\s)', t[:t.index(key)])
            last = d[-1] if d else ''
            if l['br'] and not last and len(t.rstrip('.')) <= len(phrase) + 4:
                ok = False; ev.append(f'{phrase}: <br> 뒤 단독 줄 {t!r}')
            elif last == '.':
                ok = False; ev.append(f'{phrase}: 마침표 뒤 조각 {t!r}')
            else:
                ev.append(f'{phrase}: {"쉼표" if last == "," else "괄호" if last == "(" else "문장 안"} {t!r}')
    return ok, ' | '.join(ev)


def blocks(lines):
    g = {}
    for l in lines: g.setdefault(l['blk'], []).append(l)
    return list(g.values())


def br_sentences(b):
    return len(b) >= 2 and all(l['br'] for l in b[1:]) and all(l['text'].endswith('.') for l in b[:-1])


def br_split(*keys):
    """key 가 든 블록이 문장마다 <br> 로 끊겼는지: 첫 줄 말고는 <br> 뒤, 마지막 줄 말고는 마침표로 끝남."""
    ok, ev = True, []
    for key in keys:
        b = next((b for b in blocks(ls) if any(key in l['text'] for l in b)), None)
        if not b:
            ok = False; ev.append(f'{key}: 찾지 못함'); continue
        ok &= br_sentences(b)
        ev.append(f'{key}: ' + ' <br> '.join(l['text'] for l in b))
    return ok, ' | '.join(ev)


def kept_br():
    """입력에서 이미 문장마다 <br> 로 끊겨 있던 블록이 산출물에 같은 줄 구성으로 남았는지."""
    want = [tuple(l['text'] for l in b) for b in blocks(doc_lines(src)) if br_sentences(b)]
    have = {tuple(l['text'] for l in b) for b in blocks(ls) if br_sentences(b)}
    lost = [w for w in want if w not in have]
    return bool(want) and not lost, f'입력의 <br> 블록 {len(want)}곳, 유실 {[" <br> ".join(w) for w in lost]}'


def facts(*toks):
    need = Counter(toks)
    cnt = {t: len(re.findall(r'(?<![0-9/.:])' + re.escape(t) + r'(?![0-9])', vis)) for t in need}
    miss = [f'{t}({cnt[t]}/{n})' for t, n in need.items() if cnt[t] < n]
    return not miss, f'누락 {miss}' if miss else f'{len(toks)}개 모두 있음'


def br_clean():
    last, full = run_script('check_br.py')
    return last == 'violations: 0', full


def lexical_clean():
    last, full = run_script('check_lexical.py')
    manual_only = full and all(('(수동 확인)' in blk.splitlines()[0]) for blk in re.split(r'\n(?=## )', full.rsplit('\nhits:', 1)[0]) if blk.startswith('## '))
    return last == 'hits: 0' or (manual_only and '예외' in report), full


def words(pat):
    hit = re.findall(rf'[^\n]{{0,10}}(?:{pat})[^\n]{{0,10}}', vis)
    return not hit, f'잔존 {hit}'


def reported():
    ok = bool(re.search(r'check_br|§ ?9\.1', report)) and bool(re.search(r'violations\W{0,3}0(?![0-9])', report))
    return ok, '보고에 §9.1 violations: 0 ' + ('있음' if ok else '없음' if report else '(report.md 없음)')


CHECKS = {
    0: lambda: [br_clean(), tails(('기본 θ 15%', '15%', None), ('재검증 예정', '재검증', None)), lexical_clean(),
                facts('5건', '2건', '15%', '24시간', '3건', '12%', '4/12', '2건'), reported()],
    1: lambda: [br_clean(), tails(('기본 θ 15%', '15%', None), ('최대 3회', '3회', None), ('12%', '12%', 'js')),
                words(r'저희|발화|(?:이|가|은|는) 아니라'),
                facts('5건', '2건', '3건', '15%', '10분', '3회', '24시간', '4/12', '12%', '8/29', '9/1'), kept_br(), reported()],
    2: lambda: [br_clean(), tails(('기본 θ 15%', '15%', None), ('쿨다운 24시간', '24시간', None), ('최대 2일', '2일', None), ('토·일 θ 20%', '20%', None)),
                br_split('2회', '00:10'), facts('00:10', '15%', '24시간', '2일', '20%', '2회')],
}
results = CHECKS[EID]() if doc else [(False, f'산출물 없음: {html_path}')] * len(A)
assert len(results) == len(A), f'eval {EID}: 단언 {len(A)}개, 검사 {len(results)}개'
exp = [{'text': t, 'passed': bool(ok), 'evidence': ev} for t, (ok, ev) in zip(A, results)]

p = sum(e['passed'] for e in exp); n = len(exp)
timing = json.loads((run / 'timing.json').read_text()) if (run / 'timing.json').exists() else {}
g = {'expectations': exp, 'summary': {'passed': p, 'failed': n - p, 'total': n, 'pass_rate': round(p / n, 4)},
     'execution_metrics': {'output_chars': len(doc) + len(report), **timing},
     'claims': [], 'user_notes_summary': {'uncertainties': [], 'needs_review': [], 'workarounds': []}}
(run / 'grading.json').write_text(json.dumps(g, ensure_ascii=False, indent=2))
print(f'{run}: {p}/{n}')
for e in exp: print(('  PASS ' if e['passed'] else '  FAIL ') + e['text'] + '\n        ' + str(e['evidence'])[:300].replace('\n', ' | '))
