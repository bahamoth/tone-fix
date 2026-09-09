#!/usr/bin/env python3
"""tone-fix 3단계 §9.1 구조 검출기 — HTML 산출물의 문장 경계 `<br>` 누락.

용법:
    python3 scripts/check_br.py <file.html>...

- 대상: `<p>`·`<dd>`·`<li>`·`<small>` 본문과 인라인 `<script>` 안의 문자열
  (`innerHTML` 주입용 desc·read·doc 류 값).
- 판정: `<br>` 로 나눈 세그먼트에서 태그를 지운 뒤 문장 종결 마침표 뒤에 텍스트가
  이어지면 위반. 마침표 뒤 공백을 요구하므로 소수점·URL·말줄임표는 오탐되지 않는다.
- 마지막 줄 `violations: N` 이 0 이어야 통과.
- 위반 처리: 뒤 조각이 완결 문장이면 마침표 뒤 `<br>`, 명사구 꼬리면 마침표를 쉼표(`, `) 또는 괄호로. 가운뎃점은 쓰지 않는다(§8.15).
- 알려진 오탐: `e.g.`·`vs.` 같은 약어. 좁은 블록에서는 `예:`·`대` 로 바꿔 쓴다.
"""
import re
import sys

END = re.compile(r'''[가-힣%)\]'"’”」』a-zA-Z0-9]\.\s+\S''')
BLOCK = re.compile(r'<(p|dd|li|small)\b[^>]*>(.*?)</\1>', re.S)
STR = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`')


def check(path):
    s = open(path, encoding='utf-8').read()
    targets = [(m.group(1), m.start(), m.group(2)) for m in BLOCK.finditer(s)]
    masked = BLOCK.sub(lambda m: ' ' * len(m.group(0)), s)
    for sm in re.finditer(r'<script\b[^>]*>(.*?)</script>', masked, re.S):
        targets += [('js', sm.start(1) + m.start(), m.group(0)[1:-1]) for m in STR.finditer(sm.group(1))]
    viol = 0
    for kind, pos, body in targets:
        for seg in re.split(r'<br\s*/?>', body):
            txt = re.sub(r'<[^>]+>', '', seg).replace('\\n', ' ').replace('\n', ' ').strip()
            if END.search(txt):
                viol += 1
                print(f'[{kind} L{s.count(chr(10), 0, pos) + 1}] {path}: {txt[:150]}')
    return viol


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    total = sum(check(p) for p in argv)
    print('violations:', total)
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
