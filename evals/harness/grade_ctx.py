"""문맥 판독 eval 채점: python3 grade_ctx.py <run_dir> (eval-5 push-timing). 스킬 저장소의 scripts/ 를 그대로 쓴다.

심은 문맥 말투 17곳(SEEDS)의 생존 여부, 대조 문장(CONTROLS)과 사실 보존, 결정론 스크립트 0건, 보고 기록을 본다.
"""
import json, re, subprocess, sys, pathlib

run = pathlib.Path(sys.argv[1]).resolve()
eval_dir = run.parent.parent
meta = json.loads((eval_dir / 'eval_metadata.json').read_text())
A = meta['assertions']
out = run / 'outputs'
src = (eval_dir / 'inputs' / 'push-timing.md').read_text(encoding='utf-8')
md_path = out / 'push-timing.md'
md = md_path.read_text(encoding='utf-8') if md_path.exists() else ''
report = (out / 'report.md').read_text(encoding='utf-8') if (out / 'report.md').exists() else ''
SK = pathlib.Path(__file__).resolve().parents[2] / 'scripts'

# (id, 기제, 생존 판정 정규식) : 정규식이 산출물에 맞으면 생존
SEEDS = [
    ('K1', '의의 꼬리', r'시사한다|핵심 축'),
    ('K2', '의의 꼬리', r'출발점'),
    ('K3', '재진술', r'요컨대'),
    ('K4', '재진술', r'같은 이야기'),
    ('K5', '꼬리표', r'유의한 수준의 차이다'),
    ('K6', '꼬리표', r'흔히 쓰는 기준이다'),
    ('K7', '명사화', r'으로의 발송|일원화를 통한|극대화'),
    ('K8', '명사화', r'필요성에 대한 검토'),
    ('K9', '직역 숙어', r'매달린 과일'),
    ('K10', '직역 숙어', r'무거운 짐'),
    ('K11', '직역 숙어', r'테이블 위'),
    ('K12', '직역 숙어', r'하루의 끝'),
    ('K13', '과장', r'압도적'),
    ('K14', '일반론', r'신중하게 해석'),
    ('K15', '일반론', r'의사결정 문화'),
    ('K16', '논리', r'그런데 D1'),
]
alive = {k: bool(re.search(p, md)) for k, _, p in SEEDS}
insight = md.count('인사이트')
alive['K17'] = insight > 1


def run_script(name):
    if not md:
        return '', '산출물 없음'
    r = subprocess.run([sys.executable, str(SK / name), str(md_path)], capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    return (lines[-1] if lines else ''), r.stdout.strip()


exp = []
def add(text, passed, evidence):
    exp.append({'text': text, 'passed': bool(passed), 'evidence': evidence})

last, full = run_script('check_lexical.py')
blocks = [b for b in re.split(r'\n(?=## )', full.rsplit('\nhits:', 1)[0]) if b.startswith('## ')]
manual_only = bool(blocks) and all('(수동 확인)' in b.splitlines()[0] for b in blocks)
add(A[0], last == 'hits: 0' or (manual_only and '예외' in report), full[-400:])
last2, full2 = run_script('check_md_layout.py')
add(A[1], last2 == 'violations: 0', full2[-400:])

def seeds_ok(ids):
    left = [k for k in ids if alive[k]]
    return not left, f'생존: {left}'
for i, ids in [(2, ['K1', 'K2']), (3, ['K3', 'K4']), (4, ['K5', 'K6']), (5, ['K7', 'K8']),
               (6, ['K9', 'K10', 'K11', 'K12']), (7, ['K13', 'K14', 'K15']), (8, ['K16', 'K17'])]:
    ok, ev = seeds_ok(ids)
    add(A[i], ok, ev + (f', 인사이트 {insight}회' if 'K17' in ids else ''))

ctrl = {'출근 시간대': '09시 슬롯은 출근 시간대' in md or bool(re.search(r'출근 시간대', md)),
        'APNs 3분': bool(re.search(r'APNs[^\n]{0,40}3분|3분[^\n]{0,40}APNs', md))}
add(A[9], all(ctrl.values()), str(ctrl))

facts = ['7.4%', '4.1%', '41.1%', '39.9%', '1.2%p', '0.6%p', 'p<0.01', 'p=0.04', '12만', '3만', '2026-08-03', '14일', '2시간', '11분', '5.2%', '4.3%']
rows = [l for l in src.splitlines() if re.match(r'^\| \d\d시 \|', l)]
miss = [f for f in facts if f not in md]
rows_miss = [r for r in rows if r not in md]
add(A[10], not miss and not rows_miss, f'누락 수치: {miss}, 누락 표 행: {len(rows_miss)}')

rep_ok = bool(re.search(r'2c', report)) and bool(re.search(r'P\d+\.S\d+', report)) and bool(re.search(r'독립 판독', report)) and bool(re.search(r'수용|기각', report))
add(A[11], rep_ok, f"2c {bool(re.search(r'2c', report))}, 문장 ID {bool(re.search(r'P[0-9]+[.]S[0-9]+', report))}, 독립 판독 {'독립 판독' in report}, 수용/기각 {bool(re.search('수용|기각', report))}")

p = sum(e['passed'] for e in exp); n = len(exp)
removed = sum(1 for v in alive.values() if not v)
timing = json.loads((run / 'timing.json').read_text()) if (run / 'timing.json').exists() else {}
used_agent = False
sj = run / 'stream.jsonl'
if sj.exists():
    used_agent = '"name":"Agent"' in sj.read_text() or '"name": "Agent"' in sj.read_text()
g = {'expectations': exp, 'summary': {'passed': p, 'failed': n - p, 'total': n, 'pass_rate': round(p / n, 4)},
     'seeds': {'removed': removed, 'total': len(alive), 'alive': [k for k, v in alive.items() if v]},
     'execution_metrics': {'output_chars': len(md), 'source_chars': len(src), 'used_agent_tool': used_agent, **timing},
     'claims': [], 'user_notes_summary': {'uncertainties': [], 'needs_review': [], 'workarounds': []}}
(run / 'grading.json').write_text(json.dumps(g, ensure_ascii=False, indent=2))
print(f'{run}: {p}/{n}, 심은 말투 제거 {removed}/{len(alive)}, 생존 {g["seeds"]["alive"]}, Agent 사용 {used_agent}, {len(src)}→{len(md)}자')
for e in exp:
    print(('  PASS ' if e['passed'] else '  FAIL ') + e['text'][:70] + '\n        ' + str(e['evidence'])[:200].replace('\n', ' | '))
