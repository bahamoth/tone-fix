#!/usr/bin/env python3
"""A/B run 을 채점하고 사람이 읽는 대조 화면을 만든다.

용법:
    python3 evals/harness/review_ab.py evals/workspace/iteration-N

iteration 디렉터리의 eval-*/ 마다 다음을 읽는다.

- eval_metadata.json: eval_name, kind(문서 종류), file(대상 파일 이름), prompt
- inputs/<file>: 원문
- old_skill/run-1/outputs/<file>, with_skill/run-1/outputs/<file>: 두 스킬의 교정본
- reference/<file>: 선택. 사람이 승인한 교정본(과거 세션의 최종본 등)
- judge.json: 선택. 블라인드 판정 결과

iteration 디렉터리에 votes.json 을 두면 사람의 줄별 판정을 요약 표에 싣는다. 화면의 '내 판정 복사' 로 받은 목록이나
{"<eval id>:<원문 줄>": "new|old|same|both"} 꼴을 읽는다.

만드는 파일:

- <iteration>/grading.json: eval 과 스킬별 수치
- <iteration>/review.html: 원문과 교정본을 줄 단위로 맞춰 나란히 보여 주는 화면

수치는 두 스킬에 같은 잣대(저장소의 현재 scripts/)를 댄다.
판정은 화면을 읽는 사람이 한다. 화면의 줄별 판정 버튼은 브라우저에만 저장되므로, 남기려면 votes.json 으로 옮긴다.
"""
import collections
import difflib
import glob
import html
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
import check_lexical  # noqa: E402

ARMS = [("old_skill", "기존 스킬"), ("with_skill", "새 스킬")]
REF = ("reference", "과거 세션 교정본")

PATTERNS = [
    ("가운뎃점", r"[·‧ㆍ・]"),
    ("대시", r"[—–]"),
    ("'~가 아니라'", r"(?:이|가) 아니라|이 아닌 |가 아닌 "),
    ("1인칭", r"(?<![가-힣])(?:나는|내가|나도|나의|나에게|저는|제가|저희|우리(?:는|가|의)?)(?![가-힣])"),
    ("전망과 추정", r"수 있(?:다|습니다|었|고|어|는|을)|것으로 (?:보|예상|추정)|가능성|듯하|[을를ㄹ] 것이다|것입니다"),
]


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def to_lines(text, name):
    """파일 내용을 대조 단위(줄)로 바꾼다. HTML 은 보이는 글, JSON 은 문자열 값만 남긴다."""
    if text is None:
        return None
    if name.endswith((".html", ".htm")):
        t = re.sub(r"<(style|script)\b.*?</\1>", " ", text, flags=re.S | re.I)
        t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
        t = re.sub(r"<br\s*/?>", " ", t, flags=re.I)
        t = re.sub(r"</?(?:p|div|li|ul|ol|h[1-6]|tr|td|th|table|section|article|header|footer|figure|figcaption|dt|dd|dl|blockquote|summary|details|caption|thead|tbody)\b[^>]*>", "\n", t, flags=re.I)
        t = html.unescape(re.sub(r"<[^>]+>", "", t))
        return [re.sub(r"\s+", " ", ln).strip() for ln in t.split("\n") if ln.strip()]
    if name.endswith(".json"):
        try:
            data = json.loads(text)
        except ValueError:
            return [ln.rstrip() for ln in text.split("\n") if ln.strip()]
        out = []

        def walk(node, key):
            if isinstance(node, dict):
                for k, v in node.items():
                    if isinstance(v, (dict, list)) and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
                        out.append(f"[{k}]")
                    walk(v, k)
            elif isinstance(node, list):
                for v in node:
                    walk(v, key)
            elif isinstance(node, str):
                out.append(f"{key}: {node}")

        walk(data, "")
        return out
    return [ln.rstrip() for ln in text.split("\n") if ln.strip()]


def lexical(path):
    total = hard = 0
    rules = collections.Counter()
    for rule, desc, manual, found in check_lexical.find(path, check_lexical.RULES):
        total += len(found)
        if not manual:
            hard += len(found)
            rules[f"{rule} {desc.split(' (')[0]}"] += len(found)
    return {"total": total, "hard": hard, "manual": total - hard, "hard_rules": dict(rules)}


def layout(path):
    if path.endswith(".md"):
        script = "check_md_layout.py"
    elif path.endswith((".html", ".htm")):
        script = "check_br.py"
    else:
        return None
    res = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), path], capture_output=True, text=True)
    m = re.search(r"violations: (\d+)", res.stdout)
    return int(m.group(1)) if m else None


def numbers(lines):
    return collections.Counter(re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", "\n".join(lines)))


def missing(src, dst):
    return sorted(k for k, v in (src - dst).items() for _ in range(v))


def opcodes(a, b):
    return difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()


def segments(src, outs):
    """원문 줄을 기준으로 여러 교정본을 같은 행에 맞춘다. [(a, b, [교정본별 줄 목록])] 을 낸다."""
    n = len(src)
    ops = [opcodes(src, o) for o in outs]
    nocut = [set() for _ in outs]
    for k, op in enumerate(ops):
        for tag, i1, i2, _j1, _j2 in op:
            if tag != "equal":
                nocut[k].update(range(i1 + 1, i2))
    cuts = [i for i in range(n + 1) if all(i not in s for s in nocut)]
    rows = []
    for a, b in zip(cuts, cuts[1:]):
        cells = []
        for op, out in zip(ops, outs):
            js = []
            for tag, i1, i2, j1, j2 in op:
                if tag == "equal":
                    lo, hi = max(a, i1), min(b, i2)
                    js.extend(range(j1 + lo - i1, j1 + hi - i1))
                elif tag == "insert":
                    if a < i1 <= b or (i1 == 0 and a == 0):
                        js.extend(range(j1, j2))
                elif a <= i1 and i2 <= b:
                    js.extend(range(j1, j2))
            cells.append([out[j] for j in sorted(set(js))])
        rows.append((a, b, cells))
    return rows


def mark(src_text, out_text):
    """교정본에서 새로 들어온 말은 <ins>, 원문에서 빠진 말은 <del> 로 감싼다."""
    a = re.findall(r"\s+|[^\s]+", src_text)
    b = re.findall(r"\s+|[^\s]+", out_text)
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            out.append(html.escape("".join(b[j1:j2])))
            continue
        if tag in ("delete", "replace"):
            gone = "".join(a[i1:i2]).strip()
            if gone:
                out.append(f" <del>{html.escape(gone)}</del> ")
        if tag in ("insert", "replace"):
            new = "".join(b[j1:j2])
            lead = new[: len(new) - len(new.lstrip())]
            tail = new[len(new.rstrip()):] if new.strip() else ""
            if new.strip():
                out.append(f"{html.escape(lead)}<ins>{html.escape(new.strip())}</ins>{html.escape(tail)}")
            else:
                out.append(html.escape(new))
    return "".join(out)


def grade_arm(src_path, src_lines, out_path, name, ref_changed):
    text = read(out_path)
    if text is None:
        return None
    lines = to_lines(text, name)
    joined = "\n".join(lines)
    ko_src = len(re.findall(r"[가-힣]", "\n".join(src_lines)))
    ko_out = len(re.findall(r"[가-힣]", joined))
    changed = set()
    for tag, i1, i2, _j1, _j2 in opcodes(src_lines, lines):
        if tag != "equal":
            changed.update(range(i1, max(i2, i1 + 1)))
    changed &= set(range(len(src_lines)))
    code_src = set(re.findall(r"`[^`\n]+`", read(src_path) or ""))
    g = {
        "lexical": lexical(out_path),
        "layout": layout(out_path),
        "numbers_missing": missing(numbers(src_lines), numbers(lines)),
        "code_missing": sorted(c for c in code_src if c not in text),
        "korean_chars": ko_out,
        "length_change_pct": round((ko_out - ko_src) / max(ko_src, 1) * 100, 1),
        "lines_changed": len(changed),
        "lines_total": len(src_lines),
        "patterns": {k: len(re.findall(p, joined)) for k, p in PATTERNS},
    }
    if ref_changed is not None:
        g["reference_hits"] = len(changed & ref_changed)
        g["reference_total"] = len(ref_changed)
    if name.endswith(".json"):
        try:
            json.loads(text)
            g["json_valid"] = True
        except ValueError:
            g["json_valid"] = False
    timing = read(os.path.join(os.path.dirname(os.path.dirname(out_path)), "timing.json"))
    if timing:
        t = json.loads(timing)
        g["tokens"], g["seconds"] = t.get("total_tokens"), t.get("total_duration_seconds")
    return g, lines


def collect(it_dir):
    evals = []
    for ev in sorted(glob.glob(os.path.join(it_dir, "eval-*")), key=lambda p: int(re.search(r"eval-(\d+)", p).group(1))):
        meta = json.loads(read(os.path.join(ev, "eval_metadata.json")) or "{}")
        name = meta.get("file")
        if not name:
            continue
        src_path = os.path.join(ev, "inputs", name)
        src_lines = to_lines(read(src_path), name)
        if src_lines is None:
            continue
        ref_lines = to_lines(read(os.path.join(ev, REF[0], name)), name)
        ref_changed = None
        if ref_lines is not None:
            ref_changed = set()
            for tag, i1, i2, _j1, _j2 in opcodes(src_lines, ref_lines):
                if tag != "equal":
                    ref_changed.update(range(i1, i2))
        src_joined = "\n".join(src_lines)
        entry = {
            "id": meta.get("eval_id"), "name": meta.get("eval_name"), "kind": meta.get("kind", ""), "file": name,
            "prompt": meta.get("prompt", ""), "source": meta.get("source", ""), "dir": ev,
            "input": {"lexical": lexical(src_path), "layout": layout(src_path),
                      "korean_chars": len(re.findall(r"[가-힣]", src_joined)), "lines_total": len(src_lines),
                      "patterns": {k: len(re.findall(p, src_joined)) for k, p in PATTERNS}},
            "arms": {}, "texts": [], "labels": [], "keys": [],
        }
        for key, label in ARMS:
            out_path = os.path.join(ev, key, "run-1", "outputs", name)
            res = grade_arm(src_path, src_lines, out_path, name, ref_changed)
            if res:
                entry["arms"][key] = res[0]
                entry["texts"].append(res[1]); entry["labels"].append(label); entry["keys"].append(key)
        if ref_lines is not None:
            entry["texts"].append(ref_lines); entry["labels"].append(REF[1]); entry["keys"].append(REF[0])
        entry["src_lines"] = src_lines
        judge = read(os.path.join(ev, "judge.json"))
        if judge:
            entry["judge"] = json.loads(judge)
        evals.append(entry)
    return evals


CSS = """
:root{--bg:#f7f6f3;--panel:#fff;--ink:#1d1d1f;--mute:#6b6b70;--line:#e2e0da;--accent:#0b57d0;
--ins-bg:#d9f2e0;--ins-ink:#0b4a22;--del-ink:#b3261e;--old:#8a5a00;--new:#0b57d0;--ref:#6a3fb5;--chip:#efede7;--warn:#b3261e;--ok:#1a7f37}
@media (prefers-color-scheme:dark){:root{--bg:#16171a;--panel:#1f2125;--ink:#e8e8ea;--mute:#9a9aa2;--line:#33363c;--accent:#8ab4f8;
--ins-bg:#143d24;--ins-ink:#b6f0c6;--del-ink:#ff8a80;--old:#e3b341;--new:#8ab4f8;--ref:#c4a7ff;--chip:#2a2d33;--warn:#ff8a80;--ok:#7ee2a0}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 "Pretendard","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif;word-break:keep-all;overflow-wrap:anywhere}
header.top{padding:28px 24px 8px;max-width:1500px;margin:0 auto}
h1{font-size:24px;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:19px;margin:0 0 4px}
h3{font-size:14px;margin:18px 0 6px;color:var(--mute);font-weight:600}
p{margin:4px 0}
.mute{color:var(--mute)}
a{color:var(--accent)}
main{max-width:1500px;margin:0 auto;padding:0 24px 80px}
nav{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:8px 24px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
nav a{font-size:13px;text-decoration:none;color:var(--ink);background:var(--chip);padding:3px 10px;border-radius:999px}
nav label{font-size:13px;color:var(--mute);margin-left:10px;white-space:nowrap}
section{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px;margin:20px 0}
table{border-collapse:collapse;width:100%}
.tw{overflow-x:auto}
table.sum th,table.sum td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:right;font-variant-numeric:tabular-nums;font-size:13.5px;white-space:nowrap}
table.sum th:first-child,table.sum td:first-child{text-align:left;white-space:normal}
table.sum th{color:var(--mute);font-weight:600}
.old{color:var(--old)}.new{color:var(--new)}.refc{color:var(--ref)}
.bad{color:var(--warn);font-weight:600}.good{color:var(--ok);font-weight:600}
table.diff{table-layout:fixed;margin-top:8px}
table.diff th{position:sticky;top:44px;background:var(--panel);z-index:2;text-align:left;font-size:13px;padding:6px 10px;border-bottom:2px solid var(--line)}
table.diff td{vertical-align:top;padding:8px 10px;border-bottom:1px solid var(--line);white-space:pre-wrap;font-size:14px}
table.diff td.src{color:var(--mute)}
table.diff td.same{color:var(--mute);font-style:italic;font-size:12.5px}
tr.eq td{font-size:12.5px;color:var(--mute);padding:3px 10px}
body.onlychanged tr.eq{display:none}
tr.gap td{font-size:12px;color:var(--mute);text-align:center;padding:2px;background:var(--bg);cursor:pointer}
body:not(.onlychanged) tr.gap{display:none}
ins{background:var(--ins-bg);color:var(--ins-ink);text-decoration:none;border-radius:3px;padding:0 2px}
del{color:var(--del-ink);text-decoration:line-through;opacity:.75}
body.hidedel del{display:none}
body.hide-ref .c-reference{display:none}
td.vote{width:118px;white-space:normal!important}
td.vote button{font:inherit;font-size:12px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:6px;padding:1px 6px;margin:1px;cursor:pointer}
td.vote button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.chips span{display:inline-block;background:var(--chip);border-radius:6px;padding:1px 8px;margin:2px 4px 2px 0;font-size:12.5px}
.tally{font-size:13px;margin-top:6px}
button.copy{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:8px;padding:4px 12px;cursor:pointer}
code{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;background:var(--chip);padding:1px 5px;border-radius:4px}
details{margin-top:8px}summary{cursor:pointer;color:var(--mute);font-size:13px}
@media (max-width:800px){main,header.top,nav{padding-left:16px;padding-right:16px}table.diff{min-width:900px}}
"""

JS = """
const KEY='tone-fix-review:'+document.body.dataset.iter;
const SAVED=__SAVED__;
let votes={};try{votes=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
if(!Object.keys(votes).length)votes=Object.assign({},SAVED);
function save(){try{localStorage.setItem(KEY,JSON.stringify(votes))}catch(e){}}
function paint(){
  document.querySelectorAll('td.vote').forEach(td=>{const v=votes[td.dataset.row];td.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.v===v))});
  document.querySelectorAll('section[data-eval]').forEach(sec=>{
    const c={};sec.querySelectorAll('td.vote').forEach(td=>{const v=votes[td.dataset.row];if(v)c[v]=(c[v]||0)+1});
    const n=sec.querySelectorAll('td.vote').length;const done=Object.values(c).reduce((a,b)=>a+b,0);
    sec.querySelector('.tally').textContent='내 판정: '+done+' / '+n+'행'+(done?' (새 스킬 '+(c.new||0)+', 기존 스킬 '+(c.old||0)+', 비슷 '+(c.same||0)+', 둘 다 어색 '+(c.both||0)+')':'');
  });
  const all={};Object.values(votes).forEach(v=>all[v]=(all[v]||0)+1);
  document.getElementById('total').textContent='전체 판정: 새 스킬 '+(all.new||0)+', 기존 스킬 '+(all.old||0)+', 비슷 '+(all.same||0)+', 둘 다 어색 '+(all.both||0);
}
document.addEventListener('click',e=>{
  const b=e.target.closest('td.vote button');
  if(b){const row=b.parentElement.dataset.row;if(votes[row]===b.dataset.v)delete votes[row];else votes[row]=b.dataset.v;save();paint();return}
  const g=e.target.closest('tr.gap');
  if(g){let r=g.previousElementSibling;while(r&&r.classList.contains('eq')){r.style.display='table-row';r=r.previousElementSibling}g.style.display='none'}
});
document.getElementById('onlychanged').addEventListener('change',e=>document.body.classList.toggle('onlychanged',e.target.checked));
document.getElementById('showdel').addEventListener('change',e=>document.body.classList.toggle('hidedel',!e.target.checked));
document.getElementById('showref').addEventListener('change',e=>document.body.classList.toggle('hide-ref',!e.target.checked));
document.getElementById('copy').addEventListener('click',()=>{
  const out=[];document.querySelectorAll('td.vote').forEach(td=>{const v=votes[td.dataset.row];if(v)out.push({row:td.dataset.row,vote:v,source:td.parentElement.querySelector('td.src').textContent.slice(0,80)})});
  const text=JSON.stringify(out,null,1);
  (navigator.clipboard?navigator.clipboard.writeText(text):Promise.reject()).then(()=>{document.getElementById('copy').textContent='복사했습니다'}).catch(()=>{const ta=document.getElementById('dump');ta.style.display='block';ta.value=text;ta.select()});
});
paint();
"""


def num(v):
    return "없음" if v is None else f"{v:,}" if isinstance(v, int) else str(v)


def cmp_cls(old, new, lower_better=True):
    if old is None or new is None or old == new:
        return "", ""
    better_new = (new < old) if lower_better else (new > old)
    return ("bad", "good") if better_new else ("good", "bad")


VOTE_LABEL = (("new", "새"), ("old", "기존"), ("same", "비슷"), ("both", "둘 다 어색"))


def load_votes(it_dir):
    raw = read(os.path.join(it_dir, "votes.json"))
    if not raw:
        return {}
    data = json.loads(raw)
    if isinstance(data, list):
        data = {d["row"]: d["vote"] for d in data}
    return data


def vote_count(votes, eval_id):
    c = collections.Counter(v for row, v in votes.items() if row.split(":")[0] == str(eval_id))
    return {k: c[k] for k, _ in VOTE_LABEL if c[k]}


def summary_table(evals):
    rows = []
    head = ("<tr><th>문서</th><th>종류</th><th>스캐너 위반<br>원문</th><th class=old>기존</th><th class=new>새</th>"
            "<th>수치 누락<br><span class=old>기존</span></th><th class=new>새</th>"
            "<th>분량 변화<br><span class=old>기존</span></th><th class=new>새</th>"
            "<th>바뀐 줄<br><span class=old>기존</span></th><th class=new>새</th>"
            "<th>세션 교정 지점<br><span class=old>기존</span></th><th class=new>새</th>"
            "<th>토큰(백만)<br><span class=old>기존</span></th><th class=new>새</th><th>블라인드 판정<br>(참고)</th><th>사람 판정<br>(votes.json)</th></tr>")
    for e in evals:
        o, n = e["arms"].get("old_skill"), e["arms"].get("with_skill")

        def pick(arm, f):
            return f(arm) if arm else None

        def cell(v, cls=""):
            return f"<td class='{cls}'>{'대기' if v is None else v}</td>"

        lo, ln = pick(o, lambda a: a["lexical"]["hard"]), pick(n, lambda a: a["lexical"]["hard"])
        c1 = cmp_cls(lo, ln)
        mo, mn = pick(o, lambda a: len(a["numbers_missing"])), pick(n, lambda a: len(a["numbers_missing"]))
        c2 = cmp_cls(mo, mn)
        ref = lambda a: f"{a['reference_hits']} / {a['reference_total']}" if "reference_total" in a else "해당 없음"  # noqa: E731
        tok = lambda a: f"{a['tokens'] / 1e6:.2f}" if a.get("tokens") else "없음"  # noqa: E731
        j = e.get("judge") or {}
        jc = j.get("count") or {}
        jv = f"{j['overall']} (새 {jc.get('새 스킬', 0)}, 기존 {jc.get('기존 스킬', 0)}, 비슷 {jc.get('비슷', 0)})" if j.get("overall") else "없음"
        hc = e.get("votes") or {}
        hv = ", ".join(f"{lab} {hc[k]}" for k, lab in VOTE_LABEL if k in hc) or "없음"
        rows.append(
            f"<tr><td><a href='#e{e['id']}'>{html.escape(e['name'])}</a></td><td>{html.escape(e['kind'])}</td>"
            f"<td>{e['input']['lexical']['hard']}</td>{cell(lo, c1[0])}{cell(ln, c1[1])}{cell(mo, c2[0])}{cell(mn, c2[1])}"
            f"{cell(pick(o, lambda a: str(a['length_change_pct']) + '%'))}{cell(pick(n, lambda a: str(a['length_change_pct']) + '%'))}"
            f"{cell(pick(o, lambda a: str(a['lines_changed']) + ' / ' + str(a['lines_total'])))}{cell(pick(n, lambda a: str(a['lines_changed']) + ' / ' + str(a['lines_total'])))}"
            f"{cell(pick(o, ref))}{cell(pick(n, ref))}{cell(pick(o, tok))}{cell(pick(n, tok))}"
            f"<td>{html.escape(jv)}</td><td>{html.escape(hv)}</td></tr>")
    return f"<div class=tw><table class=sum>{head}{''.join(rows)}</table></div>"


def metrics_block(e):
    rows = []
    cols = [("원문", e["input"], "")] + [(lab, e["arms"].get(k), c) for (k, lab), c in zip(ARMS, ("old", "new"))]
    head = "<tr><th>항목</th>" + "".join(f"<th class='{c}'>{lab}</th>" for lab, _a, c in cols) + "</tr>"

    def row(label, f):
        tds = "".join(f"<td>{'대기' if a is None else f(a)}</td>" for _l, a, _c in cols)
        rows.append(f"<tr><td>{label}</td>{tds}</tr>")

    row("스캐너 위반(수동 확인 제외)", lambda a: num(a["lexical"]["hard"]))
    row("스캐너 수동 확인", lambda a: num(a["lexical"]["manual"]))
    row("레이아웃 위반", lambda a: num(a.get("layout")))
    row("한글 글자 수", lambda a: num(a["korean_chars"]) + (f" ({a['length_change_pct']:+}%)" if "length_change_pct" in a else ""))
    row("수치 누락", lambda a: (f"{len(a['numbers_missing'])}건" + (": " + ", ".join(a["numbers_missing"][:10]) if a["numbers_missing"] else "")) if "numbers_missing" in a else "")
    row("코드 표기 누락", lambda a: num(len(a["code_missing"])) if "code_missing" in a else "")
    for k, _p in PATTERNS:
        row(k, lambda a, k=k: num(a["patterns"][k]))
    out = f"<div class=tw><table class=sum>{head}{''.join(rows)}</table></div>"
    for (k, lab), c in zip(ARMS, ("old", "new")):
        a = e["arms"].get(k)
        if a and a["lexical"]["hard_rules"]:
            chips = "".join(f"<span>{html.escape(r)} {n}</span>" for r, n in a["lexical"]["hard_rules"].items())
            out += f"<p class=chips><b class='{c}'>{lab}에 남은 위반</b> {chips}</p>"
    return out


def diff_table(e):
    if not e["texts"]:
        return "<p class=mute>아직 교정본이 없습니다.</p>"
    cls = {"old_skill": "old", "with_skill": "new", "reference": "refc"}
    width = 118 if len([k for k in e["keys"] if k != "reference"]) == 2 else 0
    head = "<tr><th>원문</th>" + "".join(f"<th class='{cls[k]} c-{k}'>{lab}</th>" for k, lab in zip(e["keys"], e["labels"]))
    head += "<th style='width:118px'>판정</th></tr>" if width else "</tr>"
    body, eq_run, idx = [], 0, 0
    span = len(e["keys"]) + 1 + (1 if width else 0)

    def flush():
        nonlocal eq_run
        if eq_run:
            body.append(f"<tr class=gap><td colspan={span}>바뀌지 않은 {eq_run}줄 (눌러서 펼치기)</td></tr>")
            eq_run = 0

    for a, b, cells in segments(e["src_lines"], e["texts"]):
        src = e["src_lines"][a:b]
        arms_changed = [c != src for c, k in zip(cells, e["keys"]) if k != "reference"]
        if not any(c != src for c in cells):
            body.append(f"<tr class=eq><td colspan={span}>{html.escape(chr(10).join(src))}</td></tr>")
            eq_run += 1
            continue
        flush()
        idx += 1
        tds = [f"<td class=src>{html.escape(chr(10).join(src))}</td>"]
        for c, k in zip(cells, e["keys"]):
            if c == src:
                tds.append(f"<td class='same c-{k}'>원문 그대로</td>")
            else:
                tds.append(f"<td class='c-{k}'>{mark(chr(10).join(src), chr(10).join(c))}</td>")
        if width:
            if any(arms_changed) and cells[0] != cells[1]:
                tds.append(f"<td class=vote data-row='{e['id']}:{a}'><button data-v=new>새 스킬</button><button data-v=old>기존</button>"
                           "<button data-v=same>비슷</button><button data-v=both>둘 다 어색</button></td>")
            else:
                tds.append("<td class=mute style='font-size:12px'>두 결과 같음</td>" if any(arms_changed) else "<td></td>")
        body.append(f"<tr>{''.join(tds)}</tr>")
    flush()
    return f"<div class=tw><table class=diff>{head}{''.join(body)}</table></div>"


def judge_block(e):
    j = e.get("judge")
    if not j:
        return ""
    out = ["<h3>블라인드 판정(참고)</h3>"]
    out.append(f"<p>{html.escape(j.get('summary', ''))}</p>")
    out.append("<details><summary>대목별 판정과 내용 변형 지적</summary>")
    for item in j.get("items", []):
        src = item.get("src", "")
        head = f"<span class=mute>{html.escape(src)}</span><br>" if src else ""
        out.append(f"<p class=chips><span>{html.escape(item.get('winner', ''))}</span>{head}{html.escape(item.get('reason', ''))}</p>")
    for arm, lost in (j.get("info_loss") or {}).items():
        if lost:
            rows = "".join(f"<li>{html.escape(x)}</li>" for x in lost)
            out.append(f"<p><b>{html.escape(arm)}의 내용 변형 지적</b></p><ul>{rows}</ul>")
    out.append("</details>")
    return "".join(out)


def render(it_dir, evals, votes):
    name = os.path.basename(os.path.abspath(it_dir))
    nav = "".join(f"<a href='#e{e['id']}'>{html.escape(e['kind'])}: {html.escape(e['name'])}</a>" for e in evals)
    parts = [f"<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>tone-fix 스킬 대조 {html.escape(name)}</title><style>{CSS}</style></head>"
             f"<body class='onlychanged' data-iter='{html.escape(name)}'>",
             "<header class=top><h1>tone-fix 기존 스킬과 새 스킬 대조</h1>"
             "<p class=mute>같은 원문을 두 스킬로 교정한 결과입니다. 초록 바탕은 새로 들어온 말, 빨간 취소선은 원문에서 빠진 말입니다.</p></header>",
             f"<nav>{nav}<label><input type=checkbox id=onlychanged checked> 바뀐 줄만</label>"
             "<label><input type=checkbox id=showdel checked> 빠진 말 표시</label>"
             "<label><input type=checkbox id=showref checked> 과거 세션 교정본</label></nav><main>",
             "<section><h2>요약</h2>"
             "<p class=mute>스캐너 위반은 저장소의 현재 <code>check_lexical.py</code> 로 두 결과를 같이 잰 값입니다. "
             "세션 교정 지점은 과거 세션에서 실제로 고쳐진 원문 줄 가운데 각 스킬도 고친 줄 수입니다.</p>",
             summary_table(evals),
             "<p class=tally id=total></p><p><button class=copy id=copy>내 판정 복사</button></p>"
             "<textarea id=dump style='display:none;width:100%;height:120px'></textarea></section>"]
    for e in evals:
        parts.append(f"<section id='e{e['id']}' data-eval='{e['id']}'><h2>{html.escape(e['kind'])}: {html.escape(e['name'])}</h2>"
                     f"<p class=mute>{html.escape(e['source'])}</p>"
                     f"<details><summary>지시문과 파일 위치</summary><p>{html.escape(e['prompt'])}</p><p><code>{html.escape(e['dir'])}</code></p></details>"
                     f"<h3>수치</h3>{metrics_block(e)}{judge_block(e)}"
                     f"<h3>줄별 대조</h3><p class=tally></p>{diff_table(e)}</section>")
    saved = json.dumps(votes, ensure_ascii=False).replace("</", "<\\/")
    parts.append(f"</main><script>{JS.replace('__SAVED__', saved)}</script></body></html>")
    return "".join(parts)


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    it_dir = argv[0]
    evals = collect(it_dir)
    votes = load_votes(it_dir)
    for e in evals:
        e["votes"] = vote_count(votes, e["id"])
    grading = [{k: v for k, v in e.items() if k not in ("texts", "labels", "keys", "src_lines")} for e in evals]
    with open(os.path.join(it_dir, "grading.json"), "w", encoding="utf-8") as fh:
        json.dump(grading, fh, ensure_ascii=False, indent=2)
    out = os.path.join(it_dir, "review.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render(it_dir, evals, votes))
    for e in evals:
        o, n = e["arms"].get("old_skill"), e["arms"].get("with_skill")
        print(f"eval {e['id']} {e['name']}: 스캐너 위반 원문 {e['input']['lexical']['hard']}, "
              f"기존 {o['lexical']['hard'] if o else '대기'}, 새 {n['lexical']['hard'] if n else '대기'}")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
