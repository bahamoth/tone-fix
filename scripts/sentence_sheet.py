#!/usr/bin/env python3
"""tone-fix 2c단계 판독표: 문단, 문장 번호와 측정치 (§12).

용법:
    python3 scripts/sentence_sheet.py <file.md|file.html>...

검출기가 아니다. 문서를 문단(P), 문장(S) 단위로 번호를 붙여 펼치고, 읽으면서 세기
어려운 측정치 세 가지를 덧붙인다. 판정은 references/tone-rules.md §12 판별 질문으로 한다.

- 판독표: `P07 L42 [리드]` 문단 줄 아래 `  S1 ...` 문장 줄. 역할은 제목, 리드(볼드 문장),
  본문, 목록, 표, 인용. 인용은 읽기만 하고 고치지 않는다
- 반복 어휘(§12.9): 제목에 나오지 않는 한글 낱말이 본문에 3회 이상 나오면 횟수와 위치
- 재진술 후보(§12.2): 같은 절의 앞선 리드나 문단 첫 문장과 내용어가 절반 이상 겹치는 문장
- 연속 판정 어미(§12.9): '명사 + 다', '~이다', 형용사 종결 문장이 한 묶음에서 4번 이상 연속

통과 기준이 없다. 측정치는 먼저 볼 곳일 뿐이고, 측정치에 없는 문단도 전부 판독한다.
"""
import html
import re
import sys
from collections import defaultdict

HEAD = re.compile(r'^(#{1,6})\s+(.*)')
LIST = re.compile(r'^(\s*)([-*+]|\d+[.)])\s+')
TABLE = re.compile(r'^\s*\|')
TABLE_SEP = re.compile(r'^\s*\|?\s*:?-{2,}')
FENCE = re.compile(r'^\s*(```|~~~)')
BOLD_LEAD = re.compile(r'^\*\*[^*]+\*\*')

JOSA = sorted(set('''은 는 이 가 을 를 의 에 에서 에게 로 으로 와 과 도 만 까지 부터 처럼 보다 이나 나
이며 며 이고 이다 에는 에서는 으로는 로는 에도 에서도 라는 이라는 이란 란 인 에서의 으로의 로의 과의 와의
만의 이면 이든 든 마다 께서 한테 이라 라 이라고 라고 야 이야'''.split()), key=len, reverse=True)
VERB_TAIL = sorted(set('''한다 하는 하고 하며 해서 하면 하지 했다 하여 할 한 함 하게 하기 된다 되는 되고 되어
됐다 된 됨 되며 되면 시킨다 시키는 적인 적으로 스럽다 스러운 했고 했으며 합니다 됩니다 하던 되던 받는 받아
받은 준다 주는 둔다 두는 쓴다 쓰는 낸다 내는 본다 보는 있는 없는 있다 없다 있고 없고 이다 였다 이었다'''.split()), key=len, reverse=True)
STOP = set('''이번 모든 각 같은 같이 통해 대한 위해 따라 경우 때문 정도 이상 이하 이후 이전 그 이 저 것 수 등 및
또는 또한 그리고 하지만 다만 먼저 다음 현재 기존 대해 관련 위한 통한 함께 모두 가장 더 매우 바로 이미 아직 다시
계속 처음 지금 이것 이는 이를 그대로 하나 둘 셋 경우 부분 때 중 안 밖 위 아래 앞 뒤 전 후 간 내 외 별 당 약
그런데 따라서 그래서 즉 결국 오히려 반면 우선 특히 주로 실제 실제로 여기 거기 무엇 어떤 어디 누구 왜 한 두 세 네
다른 따르면 없이 전에 일부 쓰고 하는 위해서 대해서 통해서 가지 개 건 명 곳 번 차 회
않고 않는 않은 아니 아닌 달라 따로 전후 높은 낮은 같은 많은 적은 큰 작은'''.split())


def strip_md(t):
    t = re.sub(r'`[^`]*`', ' X ', t)
    t = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', t)
    t = re.sub(r'https?://\S+', ' ', t)
    return t.replace('**', '').replace('__', '')


def stems(text):
    t = strip_md(text)
    out = []
    for w in re.findall(r'[A-Za-z][A-Za-z0-9_.-]+', t):
        w = w.strip('.-').lower()
        if len(w) >= 2 and w != 'x':
            out.append(w)
    for w in re.findall(r'(?<![가-힣0-9%.])[가-힣]+', t):      # 5건이, 3만 명 같은 수량 단위는 제외
        if w in STOP:
            continue
        s = w
        for suf in VERB_TAIL:
            if s.endswith(suf) and len(s) - len(suf) >= 2:
                s = s[:-len(suf)]
                break
        else:
            for suf in JOSA:
                if s.endswith(suf) and len(s) - len(suf) >= 2:
                    s = s[:-len(suf)]
                    break
        if len(s) >= 2 and s not in STOP and s not in JOSA and not s.endswith('다'):
            out.append(s)
    return out


def split_sentences(t):
    out, start = [], 0
    lead = BOLD_LEAD.match(t)
    if lead and t[lead.end():].strip():         # 마침표 없는 명사구 리드도 한 문장으로 끊는다
        out.append(t[:lead.end()].strip())
        start = lead.end()
    for m in re.finditer(r'[.?!]+(\*\*|["”’」』)\]]+)*(?=\s|$)', t):
        if m.start() < start:
            continue
        before = t[max(0, m.start() - 4):m.start()]
        if re.search(r'(e\.g|i\.e|vs|etc|cf|No)$', before, re.I):
            continue
        seg = t[start:m.end()].strip()
        if seg:
            out.append(seg)
        start = m.end()
    tail = t[start:].strip()
    if tail:
        out.append(tail)
    return out


def ending_kind(s):
    """판정형(명사 + 다, ~이다, 형용사, ~하다 판정) 또는 동작형."""
    t = re.sub(r'`[^`]*`', 'X', s)
    t = re.sub(r'\([^)]*\)', '', t.replace('**', '')).strip()
    t = re.sub(r'[.!?"”’」』\s]+$', '', t)
    if not t.endswith('다') or len(t) < 2:
        return 'other'
    c = t[-2]
    if not ('가' <= c <= '힣'):
        return 'judge'                       # `codex exec`다, 1.8배다 류
    jong = (ord(c) - 0xAC00) % 28
    if c == '는' or jong in (4, 20) or c in '었았했겠':   # -ㄴ다/-는다, 과거, 있다/없다
        return 'act'
    return 'judge'


def parse_md(lines):
    units = []          # dict(role, line, text, section)
    section = ''
    in_fence = False
    cur = None

    def close():
        nonlocal cur
        if cur:
            units.append(cur)
        cur = None

    if lines and lines[0].strip() == '---':
        try:
            end = lines.index('---', 1)
            lines = [''] * (end + 1) + lines[end + 1:]
        except ValueError:
            pass
    blank_before = False
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip()
        if FENCE.match(line):
            close()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip():
            if cur and cur['role'] in ('표', '인용'):
                close()
            blank_before = True
            continue
        hm = HEAD.match(line)
        if hm:
            close()
            section = hm.group(2).strip()
            units.append({'role': '제목', 'line': i, 'text': section, 'section': section})
            blank_before = False
            continue
        if re.match(r'^\s*<[a-zA-Z/!]', line):
            close()
            continue
        if TABLE.match(line):
            if TABLE_SEP.match(line):
                continue
            row = ' | '.join(c.strip() for c in line.strip().strip('|').split('|'))
            if cur and cur['role'] == '표':
                cur['rows'].append(row)
            else:
                close()
                cur = {'role': '표', 'line': i, 'rows': [row], 'section': section}
            blank_before = False
            continue
        if line.lstrip().startswith('>'):
            body = line.lstrip()[1:].strip()
            if cur and cur['role'] == '인용':
                cur['text'] += ' ' + body
            else:
                close()
                cur = {'role': '인용', 'line': i, 'text': body, 'section': section}
            blank_before = False
            continue
        lm = LIST.match(line)
        if lm:
            close()
            cur = {'role': '목록', 'line': i, 'text': line[lm.end():].strip(), 'section': section,
                   'indent': len(lm.group(1))}
            blank_before = False
            continue
        if cur and cur['role'] == '목록' and (not blank_before or re.match(r'^\s{2,}\S', line)):
            cur['text'] += ' ' + line.strip()          # 목록 항목의 이어지는 줄, 들여쓴 부연 문단
            blank_before = False
            continue
        if cur and cur['role'] in ('본문', '리드') and not blank_before:
            cur['text'] += ' ' + line.strip()
            blank_before = False
            continue
        close()
        role = '리드' if BOLD_LEAD.match(line.strip()) else '본문'
        cur = {'role': role, 'line': i, 'text': line.strip(), 'section': section}
        blank_before = False
    close()
    return units


def parse_html(src):
    src = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', src, flags=re.S | re.I)
    units, section = [], ''
    for m in re.finditer(r'<(h[1-6]|p|li|dd|dt|td|th|small|figcaption|blockquote)\b[^>]*>(.*?)</\1>', src, re.S | re.I):
        tag, inner = m.group(1).lower(), m.group(2)
        line = src.count('\n', 0, m.start()) + 1
        inner = re.sub(r'<br\s*/?>', ' ', inner, flags=re.I)
        lead = re.match(r'\s*<(strong|b)\b', inner, re.I)
        text = html.unescape(re.sub(r'<[^>]+>', '', inner))
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            continue
        if tag.startswith('h'):
            section = text
            units.append({'role': '제목', 'line': line, 'text': text, 'section': section})
        elif tag == 'blockquote':
            units.append({'role': '인용', 'line': line, 'text': text, 'section': section})
        else:
            role = '목록' if tag == 'li' else ('표' if tag in ('td', 'th') else ('리드' if lead else '본문'))
            u = {'role': role, 'line': line, 'text': text, 'section': section}
            if role == '표':
                u = {'role': '표', 'line': line, 'rows': [text], 'section': section}
            units.append(u)
    return units


def sheet(path):
    src = open(path, encoding='utf-8').read()
    units = parse_html(src) if path.lower().endswith(('.html', '.htm')) else parse_md(src.split('\n'))
    print(f'# 판독표: {path}')
    sents = []          # (sid, role, section, text, unit_index)
    for n, u in enumerate(units, 1):
        pid = f'P{n:02d}'
        u['pid'] = pid
        if u['role'] == '표':
            print(f'{pid} L{u["line"]} [표]')
            for k, r in enumerate(u['rows'], 1):
                print(f'  R{k} {r}')
            continue
        if u['role'] == '제목':
            print(f'\n{pid} L{u["line"]} [제목] {u["text"]}')
            continue
        ss = split_sentences(u['text'])
        role = u['role']
        if role == '목록' and BOLD_LEAD.match(u['text']):
            role = '목록, 리드'
        print(f'{pid} L{u["line"]} [{role}]')
        for k, s in enumerate(ss, 1):
            print(f'  S{k} {s}')
            sents.append((f'{pid}.S{k}', u['role'], u['section'], s, n, k))

    # 반복 어휘
    head_stems = set()                  # 주제어: 제목, 볼드 리드, 표, 인라인 코드 주변 낱말
    for u in units:
        if u['role'] == '제목':
            head_stems.update(stems(u['text']))
        elif u['role'] == '표':
            for r in u['rows']:
                head_stems.update(stems(r))
        else:
            lead = BOLD_LEAD.match(u.get('text', ''))
            if lead:
                head_stems.update(stems(lead.group(0)))
    where = defaultdict(list)
    for sid, role, sec, s, *_ in sents:
        if role == '인용':
            continue
        for st in stems(s):
            if re.match(r'[가-힣]', st) and st not in head_stems:
                where[st].append(sid)
    rep = sorted(((st, ids) for st, ids in where.items() if len(ids) >= 3), key=lambda x: (-len(x[1]), x[0]))

    # 재진술 후보: 같은 절의 앞선 앵커(리드, 문단 첫 문장)와 내용어 겹침
    restate = []
    anchors = []
    cur_sec = None
    for sid, role, sec, s, ui, k in sents:
        if role == '인용':
            continue
        if sec != cur_sec:
            anchors, cur_sec = [], sec
        st = set(stems(s))
        if len(st) >= 3:
            for aid, ast, atext in anchors:
                inter = st & ast
                ratio = len(inter) / min(len(st), len(ast))
                if len(inter) >= 3 and ratio >= 0.5:
                    restate.append((sid, aid, sorted(inter), ratio))
                    break
        if k == 1 or s.startswith('**'):
            anchors.append((sid, st, s))

    # 연속 판정 어미
    runs = []
    block, prev_sec = [], None

    def flush_block():
        run = []
        for sid, kind in block + [(None, 'stop')]:
            if kind == 'judge':
                run.append(sid)
            else:
                if len(run) >= 4:
                    runs.append((run[0], run[-1], len(run)))
                run = []
    for sid, role, sec, s, ui, k in sents:
        if role in ('인용', '목록'):
            continue
        if sec != prev_sec or s.startswith('**'):
            flush_block()
            block, prev_sec = [], sec
        block.append((sid, ending_kind(s)))
    flush_block()

    print('\n## 측정치 (먼저 볼 곳. 판정은 §12 판별 질문으로)')
    print('반복 어휘 (§12.9, 제목, 볼드 리드, 표에 없는 한글 낱말 3회 이상. 주제어, 용어는 두고 평가어, 추상명사만 고른다):')
    if rep:
        by_n = defaultdict(list)
        for st, ids in rep:
            by_n[len(ids)].append(f'{st}({", ".join(ids[:4])}{" 외" if len(ids) > 4 else ""})')
        for n in sorted(by_n, reverse=True):
            print(f'  ×{n}: ' + ' / '.join(by_n[n]))
    else:
        print('  없음')
    print('재진술 후보 (§12.2, 앞선 리드나 문단 첫 문장과 내용어 절반 이상 겹침):')
    if restate:
        for sid, aid, inter, ratio in restate:
            print(f'  {sid} ↔ {aid} ({round(ratio * 100)}%): {", ".join(inter[:8])}')
    else:
        print('  없음')
    print('연속 판정 어미 (§12.9, 명사 + 다, 형용사 종결 4문장 이상 연속):')
    if runs:
        for a, b, n in runs:
            print(f'  {a} ~ {b} ({n}문장)')
    else:
        print('  없음')
    print(f'units: {len(units)}, sentences: {len(sents)}')


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    for i, p in enumerate(argv):
        if i:
            print()
        sheet(p)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
