#!/usr/bin/env python3
"""eval-8 (tutorial-revamp) 심은 표현 잔존 수와 수치 보존 확인. usage: grade_tut.py <md>..."""
import re, sys, pathlib

SEEDS = {
    '축': [r'두 축', r'세 축', r'한 축', r'주축'],
    '열다/닫다': [r'로 열고', r'로 연다', r'닫을 수 없', r'다시 연다', r'열리기도 전에'],
    '갈리다/가르다': [r'에서 갈린', r'크게 갈린', r'갈리지 않', r'떠날지를 가르'],
    'X는 Y다': [r'문제는 3단계', r'근거는 두', r'요청은 하나', r'계기는 2분기', r'핵심은 학습',
                r'관건은 트리거', r'가장 무거운 것은', r'남은 것은 실행', r'리스크는 세 갈래',
                r'문제는 UI가 아니라', r'기준은 레벨이 아니라'],
    '서술어, 비유 동사': [r'다치지 않', r'숫자가 움직', r'내려앉', r'결이 다르', r'안기고',
                     r'떠받친', r'얹혔', r'숫자로 환산하면', r'손맛', r'자리를 옮긴'],
    '조어, 숙어, 과장': [r'학습 부채', r'체감 진입 비용', r'낮게 달린 과일', r'핵심 레버',
                    r'빙산의 일각', r'큰 그림', r'압승', r'그 어느 때보다'],
    '현재형 결과': [r'13\.3%p 뛰고', r'3\.4%p 오른다', r'7\.2%p 뒤진다', r'4\.3%p 앞선다'],
    '맺음 일반론': [r'첫인사', r'방향을 가리켰', r'결론부터'],
}
FACTS = ['412,560', '58.3%', '38%', '47.1%', '9.8%', '71.4%', '58.1%', '45.3%', '41.9%',
         '2.28%', '2.31%', 'p=0.08', '64.0%', '71.2%', '26%', '1,925명', '1만 3,200원',
         '2만 1,400원', '1만 9,900원', '11월 12일', '11월 26일', '18.1%', '17.6%', '21.4%', '2.1%']

for f in sys.argv[1:]:
    t = pathlib.Path(f).read_text()
    print(f'== {f}  ({len(t)}자)')
    total = 0
    for cat, pats in SEEDS.items():
        left = [p.replace('\\', '') for p in pats if re.search(p, t)]
        total += len(left)
        print(f'  {cat:<16} {len(left)}/{len(pats)}  {", ".join(left)}')
    body = [l for l in t.splitlines() if l.strip() and not l.startswith(('|', '#'))]
    print(f'  구조: 볼드 줄 {sum(1 for l in body if l.lstrip("- ").startswith("**"))}, 콜론 라벨 줄 {sum(1 for l in body if re.match(r"^[^|]{2,30}: ", l) or l.rstrip().endswith(":"))}, 본문 줄 {len(body)}')
    miss = [x for x in FACTS if x not in t]
    print(f'  심은 표현 잔존 합계 {total}/{sum(len(v) for v in SEEDS.values())}   수치 누락 {len(miss)} {miss}')
