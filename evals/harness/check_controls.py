#!/usr/bin/env python3
"""사람 글 대조군 회귀 점검.

용법:
    python3 evals/harness/check_controls.py            # 기준선과 비교
    python3 evals/harness/check_controls.py --update   # 기준선의 건수를 현재 값으로 갱신

evals/controls/ 의 사람이 쓴 보고서에 scripts/check_lexical.py 의 규칙을 돌려
evals/controls/baseline.json 과 비교한다. 다음 두 경우에 실패한다.

- 기준선에 없는 규칙이 걸렸다. 사람이 쓴 보고서 문장을 새로 위반으로 잡는 규칙이다.
- 기준선에 있는 규칙이 기준선보다 많이 걸렸다. 정규식이 넓어졌다.

기준선에 규칙을 새로 올리려면 `--update` 로 건수를 채운 뒤 `why` 에 사유를 적는다.
사유는 그 규칙이 사람 글에도 걸리는 까닭(문체 규약, 사람 글의 번역 투 등)이다.
"""
import collections
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import check_lexical  # noqa: E402

CONTROLS = os.path.join(ROOT, "evals", "controls")
BASELINE = os.path.join(CONTROLS, "baseline.json")


def rule_key(rule, desc):
    return f"{rule} {desc.split(' (')[0]}"


def measure():
    counts, samples = collections.Counter(), {}
    files = sorted(glob.glob(os.path.join(CONTROLS, "*", "*.md")))
    for path in files:
        for rule, desc, _manual, found in check_lexical.find(path, check_lexical.RULES):
            key = rule_key(rule, desc)
            counts[key] += len(found)
            n, ln, m = found[0]
            a, b = max(0, m.start() - 20), min(len(m.string), m.end() + 12)
            samples.setdefault(key, f"{os.path.basename(path)}:{n} …{m.string[a:b].strip()}…")
    return files, counts, samples


def main(argv):
    files, counts, samples = measure()
    with open(BASELINE, encoding="utf-8") as fh:
        base = json.load(fh)
    rules = base["rules"]

    if "--update" in argv:
        for key in counts:
            rules.setdefault(key, {"hits": 0, "why": "TODO: 사람 글에도 걸리는 사유를 적는다"})
        for key in list(rules):
            rules[key]["hits"] = counts.get(key, 0)
            if not rules[key]["hits"]:
                del rules[key]
        with open(BASELINE, "w", encoding="utf-8") as fh:
            json.dump(base, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"baseline updated: {len(rules)} rules")
        return 0

    failures = 0
    print(f"controls: {len(files)} files")
    for key in sorted(set(counts) | set(rules)):
        got, allowed = counts.get(key, 0), rules.get(key, {}).get("hits", 0)
        if got > allowed:
            failures += 1
            reason = "기준선에 없는 규칙" if key not in rules else "기준선 초과"
            print(f"FAIL {key}: {got} > {allowed} ({reason})  예: {samples[key]}")
        else:
            print(f"ok   {key}: {got} <= {allowed}")
    print(f"failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
