#!/usr/bin/env python3
"""번역한 문자열이 **식별자로도 쓰이는지** 검사한다.

표시용으로 번역한 값을 다른 곳에서 `== "영어원문"` 으로 비교하면 그 비교는
영원히 실패한다.  기능이 조용히 죽거나 (economy 의 "Overworld" 처럼) 테이블
키가 어긋나 크래시가 난다.

같은 글자가 '표시용 값'과 '내부 식별자'로 따로 쓰이는 경우도 많으므로,
사람이 확인해 안전하다고 판단한 것은 SAFE 에 적어 둔다.
새로 걸리는 것이 있으면 반드시 눈으로 확인할 것.
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

WRAP = re.compile(r'_[TFDK]\s*\(\s*"((?:[^"\\]|\\.){1,60})"\s*\)')

# 확인 결과 안전한 것들 — 비교 대상 변수에 번역값이 흘러들지 않는다
SAFE = {
    # 상태/효과 id: 번역된 자리는 표시용 name/noun 이고, 비교는 useFX/effect id
    'poison', 'torpor', 'blind', 'blinding', 'stun', 'oily', 'grappled',
    'bleeding',
    # 지역 id: 번역된 자리는 displayName / economyNames 값,
    #          비교는 world_data.name / villageName / currentWorldName
    'Yarrow', 'Moon-upon-Thoss', 'Hearthaven', 'The Red Grove', 'Wintersholl',
    'Barrow-Linn', 'Harrowdus', 'Roche', '9X9-01',
    # 지도 범례 라벨: 비교는 셀/월드 id
    'ship', 'warp', 'wall', 'door', 'floor',
    # 메뉴 라벨: UICategories / gCategories 자체는 번역하지 않는다
    'Options', 'Tutorials', 'Melee', 'Ranged', 'Food', 'Confirm', 'None',
}


def lua_files(root):
    for dp, _dn, fns in os.walk(root):
        for fn in fns:
            if fn.endswith('.lua') and fn != 'loc.lua':
                yield os.path.join(dp, fn), os.path.relpath(os.path.join(dp, fn), root)


def main():
    build = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build')
    lang = os.path.join(ROOT, 'lang', 'ko.csv')
    if not os.path.isdir(build):
        print('build 폴더가 없습니다. 먼저 적용.bat 을 실행하세요.')
        return 0

    translated = set()
    with open(lang, newline='', encoding='utf-8-sig') as f:
        for r in csv.reader(f):
            if len(r) >= 4 and r[0] == 'S' and r[3].strip():
                translated.add(r[2])

    wrapped = {}
    for p, rel in lua_files(build):
        for i, line in enumerate(open(p, encoding='utf-8', errors='replace'), 1):
            for m in WRAP.finditer(line):
                lit = m.group(1)
                if lit in translated:
                    wrapped.setdefault(lit, []).append((rel, i))
    check = {k: v for k, v in wrapped.items() if k not in SAFE}
    if not check:
        print('식별자 검사: 문제 없음 (확인된 안전 목록 %d개 제외)' % len(SAFE))
        return 0

    pats = {lit: re.compile(r'[=~]=\s*"' + re.escape(lit) + r'"'
                            r'|"' + re.escape(lit) + r'"\s*[=~]=')
            for lit in check}
    hits = {}
    for p, rel in lua_files(build):
        for i, line in enumerate(open(p, encoding='utf-8', errors='replace'), 1):
            if '"' not in line:
                continue
            for lit, rx in pats.items():
                if rx.search(line):
                    hits.setdefault(lit, []).append((rel, i, line.strip()[:110]))

    if not hits:
        print('식별자 검사: 문제 없음')
        return 0

    print('식별자 검사: 확인 필요 %d건' % len(hits))
    print('  (번역했는데 다른 곳에서 영어 원문으로 비교하는 문자열입니다.')
    print('   비교 대상에 번역값이 흘러들면 그 기능이 조용히 죽습니다.)')
    print()
    for lit, found in sorted(hits.items()):
        print('■ "%s"' % lit)
        for rel, i in wrapped[lit][:2]:
            print('    번역 %s:%d' % (rel, i))
        for rel, i, line in found[:3]:
            print('    비교 %s:%d  %s' % (rel, i, line))
        print()
    print('안전하다고 확인했으면 tools/audit_ids.py 의 SAFE 에 추가하십시오.')
    return len(hits)


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
