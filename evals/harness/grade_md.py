"""MD 보고서 eval 채점: python3 grade_md.py <run_dir> (eval-3 harness-report). 스킬 저장소의 scripts/ 를 그대로 쓴다."""
import json, re, subprocess, sys, pathlib
run = pathlib.Path(sys.argv[1]).resolve()
eval_dir = run.parent.parent
meta = json.loads((eval_dir / 'eval_metadata.json').read_text())
out = run / 'outputs'
src = (eval_dir / 'inputs' / 'harness-report.md').read_text(encoding='utf-8')
md_path = out / 'harness-report.md'
md = md_path.read_text(encoding='utf-8') if md_path.exists() else ''
report = (out / 'report.md').read_text(encoding='utf-8') if (out / 'report.md').exists() else ''
SK = pathlib.Path(__file__).resolve().parents[2] / 'scripts'

def run_script(name):
    if not md: return '', '산출물 없음'
    r = subprocess.run([sys.executable, str(SK / name), str(md_path)], capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    return (lines[-1] if lines else ''), r.stdout.strip()

exp = []
def add(text, passed, evidence): exp.append({'text': text, 'passed': bool(passed), 'evidence': evidence})
A = meta['assertions']

last, full = run_script('check_lexical.py')
manual_only = full and all(('(수동 확인)' in blk.splitlines()[0]) for blk in re.split(r'\n(?=## )', full.rsplit('\nhits:', 1)[0]) if blk.startswith('## '))
add(A[0], last == 'hits: 0' or (manual_only and '예외' in report), full)

last2, full2 = run_script('check_md_layout.py')
add(A[1], last2 == 'violations: 0', full2)

body = re.sub(r'```.*?```', '', md, flags=re.S)
codes = re.findall(r'\bL[0-5]\s*[~–-]\s*L?[0-5]\b|\bL[0-5] ?(?:계층|레이어|어댑터|단계)|[0-9] ?계층\s*\(L[0-5]', body)
tree_codes = re.findall(r'#\s*L[0-5]\b', md)
add(A[2], not codes and not tree_codes, f'본문 코드: {codes[:5]}, 트리 주석: {tree_codes[:5]}')

body_after_summary = re.sub(r'^##\s*(요약|TL;?DR|Summary)[^\n]*\n.*?(?=^##\s)', '', body, count=1, flags=re.M | re.S)  # 요약 절은 정의 표보다 앞서도 됨
first_use = re.search(r'\d+\s*단계(?!\s*(구조|체계|디렉터리|로 |의 ))', body_after_summary)
tbl = re.search(r'^\|[^\n]*단계[^\n]*\|[^\n]*(이름|역할)[^\n]*\|[^\n]*(하는 일|역할|작업)[^\n]*\|', md, re.M)
add(A[3], bool(tbl) and bool(first_use) and tbl.start() <= md.find(body_after_summary[first_use.start():first_use.start()+40]) + 200, f'정의 표: {"있음" if tbl else "없음"} @ {tbl.start() if tbl else None}, N단계 첫 사용 @ {first_use.start() if first_use else None}')

conv = re.findall(r'(근거|증거|결론|의견|보고|연구|사례)[^.\n]{0,40}수렴', body)
add(A[4], not conv, f'수렴 의인화: {conv}')

m = re.search(r'^##\s*(요약|TL;?DR|Summary)[^\n]*\n(.*?)(?=^##\s)', md, re.M | re.S)
items = [i.strip() for i in re.split(r'\n(?=\s*(?:[-*+]|\d+[.)])\s)', m.group(2)) if i.strip()] if m else []
items = [i for i in items if re.match(r'\s*(?:[-*+]|\d+[.)])\s', i)]
ok_items = []
for it in items:
    b = re.match(r'\s*(?:[-*+]|\d+[.)])\s+(\*\*[^*]+\*\*)', it)
    n_s = len(re.findall(r'[가-힣a-zA-Z0-9%)\]\'"’”」』]\.(\s|$)', it.replace('**', '')))
    ok_items.append(bool(b) and len(re.sub(r'\s', '', b.group(1))) <= 60 and n_s <= 3 and len(re.sub(r'\s', '', it)) <= 200)
add(A[5], bool(items) and 3 <= len(items) <= 5 and all(ok_items), f'요약 항목 {len(items)}개, 통과 {sum(ok_items)}개')

fr = [l for l in re.findall(r'\[§8\.12[^\n]*', full2) if '(수동 확인)' not in l]
add(A[6], not fr, f'§8.12 리드 프레임: {fr[:5]}')

advs = [l for l in re.findall(r'\[§8\.12[^\n]*\(수동 확인\)[^\n]*', full2)]
adv_ok = not advs or ('사유' in report and len(re.findall(r'advisor', report)) >= 1)
add(A[7], adv_ok, f'advisories {len(advs)}건, 보고 사유 {"있음" if "사유" in report else "없음"}: {advs[:3]}')

ret = re.findall(r'[^\n]{0,20}은퇴[^\n]{0,20}', body)
add(A[8], not ret, f'은퇴: {ret}')

heads = re.findall(r'^##\s+(.*)', md, re.M)
motive = [h for h in heads if re.search(r'개요|배경|문제|동기|현황|목적|Overview|Background|Motivation|Problem', h)]
idx = [i for i, h in enumerate(heads) if h in motive]
add(A[9], bool(motive) and idx and idx[0] <= 2, f'동기 절: {motive}, 제목 순서: {heads[:4]}')

q = [h for h in re.findall(r'^#{1,6}\s+(.*)', md, re.M) if re.search(r'(인가|한가|는가|을까|할까|있나|없나)\s*$', h)]
add(A[10], not q, f'의문형 제목: {q}')

urls = set(re.findall(r'https?://[^\s)>,]+', src)); missing = [u for u in urls if u not in md]
blocks_src = re.findall(r'```.*?```', src, re.S); blocks_out = re.findall(r'```.*?```', md, re.S)
key_lines = ['orca orchestration run-create', 'gate-resolve', 'intent/', 'evals/', 'adapters/']
kept = all(any(k in b for b in blocks_out) for k in key_lines)
add(A[11], not missing and len(blocks_out) >= 2 and kept, f'URL 누락 {len(missing)}/{len(urls)}, 코드 블록 {len(blocks_src)}→{len(blocks_out)}, 핵심 줄 유지 {kept}')

st = all(re.search(p, report) for p in [r'hits', r'2a|2b|2단계', r'violations'])
add(A[12], st, '보고 단계별 기록 ' + ('있음' if st else '없음'))

two = [l for l in re.findall(r'\[(?:§8\.12 리드[^\n]*두 절|§11\.5)[^\n]*', full2)]
add(A[13], not two, f'두 절·같은 줄 부연: {two[:4]}')
deo = re.findall(r'더 (?!많이|잘|적게|자주|빨리|늦게|오래|크게|작게|높게|낮게|넓게|깊게|쉽게|어렵게|있|없)[가-힣]{0,4}(?:는다|한다|낸다|든다|쓴다|둔다|본다|준다|긴다|친다|린다|킨다|인다|운다|습니다)(?:\.|,|\s|$)', body)
add(A[14], not deo, f"'더+동사': {deo[:4]}")
doc = re.findall(r'(?:문서|보고서|글|자료)(?:는|은|가|이) [^.\n]{0,60}(?:답한다|다룬다|제안한다|보여준다|주장한다)|갈아 ?끼', body)
add(A[15], not doc, f'문서 의인화·갈아 끼: {doc[:4]}')

nofence = re.sub(r'```.*?```', '', md, flags=re.S)
nofence = re.sub(r'"[^"\n]*"|“[^”]*”', '', nofence)
dashes = re.findall(r'[^\n]{0,15}[—–][^\n]{0,15}', nofence)
dots = re.findall(r'[^\n]{0,15}·[^\n]{0,15}', re.sub(r'[월화수목금토일](·[월화수목금토일])+', '', nofence))
xref = re.findall(r'(?:이|위|아래|다음|본) ?(?:표|절|목록)[^.\n]{0,30}(?:지칭|참조|쓴다|사용한다|다룬다)|[0-9]+절(?:의|이|가) [^.\n]{0,30}(?:쓴다|참조|사용)', body)
nmz = re.findall(r'(?:바꾸는|가르는|좌우하는|유발하는) (?:임계치|임계값|기준|조건|지표)', body)
add(A[16], not dashes and not dots and not xref and not nmz, f'대시 {len(dashes)} {dashes[:2]}, 가운뎃점 {len(dots)} {dots[:2]}, 내부 참조 {xref[:2]}, 관형절 제목 {nmz[:2]}')

p = sum(e['passed'] for e in exp); n = len(exp)
timing = json.loads((run / 'timing.json').read_text()) if (run / 'timing.json').exists() else {}
g = {'expectations': exp, 'summary': {'passed': p, 'failed': n - p, 'total': n, 'pass_rate': round(p / n, 4)},
     'execution_metrics': {'output_chars': len(md) + len(report), **timing},
     'claims': [], 'user_notes_summary': {'uncertainties': [], 'needs_review': [], 'workarounds': []}}
(run / 'grading.json').write_text(json.dumps(g, ensure_ascii=False, indent=2))
print(f'{run}: {p}/{n}')
for e in exp: print(('  PASS ' if e['passed'] else '  FAIL ') + e['text'] + '\n        ' + str(e['evidence'])[:300].replace('\n', ' | '))
