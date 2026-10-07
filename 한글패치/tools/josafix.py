#!/usr/bin/env python3
"""ko.csv 의 번역문에서 %N 자리표시자 뒤에 고정된 조사를 자동선택 표기로 바꾼다.
   %1을  ->  %1을(를)      %1{white}이  ->  %1{white}이(가)
"""
import csv, io, re, sys

RULES = [
    (r'(?:이|가)',       '이(가)'),
    (r'(?:을|를)',       '을(를)'),
    (r'(?:은|는)',       '은(는)'),
    (r'(?:와|과)',       '와(과)'),
    (r'(?:으로|로)',     '(으)로'),
]
HEAD = r'(%\d(?:\{[^}]*\})*)'
TAIL = r'(?![가-힣])'
PATS = [(re.compile(HEAD + r'(?:' + a + r')' + TAIL), b) for a, b in RULES]
# 이미 표기가 들어있는 자리는 건드리지 않는다
DONE = re.compile('|'.join(re.escape(m) for m in (
    '이(가)', '가(이)', '(이)가', '을(를)', '를(을)', '(을)를',
    '은(는)', '는(은)', '(은)는', '와(과)', '과(와)', '(과)와',
    '(으)로서', '(으)로써', '(으)로는', '(으)로', '으로(로)', '로(으로)',
    '아(야)', '야(아)', '(이)여', '(이)라', '(이)란', '(이)나', '(이)든',
)))


def fix(s):
    if '%' not in s:
        return s, 0
    n = 0
    # 이미 처리된 표기를 잠시 봉인
    holes = []
    def stash(m):
        holes.append(m.group(0))
        return '\x00%d\x00' % (len(holes) - 1)
    s = DONE.sub(stash, s)
    for pat, rep in PATS:
        s, k = pat.subn(lambda m: m.group(1) + rep, s)
        n += k
    s = re.sub(r'\x00(\d+)\x00', lambda m: holes[int(m.group(1))], s)
    return s, n


def main(path, apply=False):
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    head, body = rows[0], rows[1:]
    ko_i = head.index('ko')
    total, changed = 0, []
    for r in body:
        if len(r) <= ko_i:
            continue
        new, n = fix(r[ko_i])
        if n:
            changed.append((r[ko_i], new))
            r[ko_i] = new
            total += n
    for a, b in changed[:25]:
        print('  -', a[:90])
        print('  +', b[:90])
    print('%d 행 / 조사 %d 곳 수정' % (len(changed), total))
    if apply:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator='\n')
        w.writerow(head)
        w.writerows(body)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(buf.getvalue())
        print('저장:', path)


if __name__ == '__main__':
    main(sys.argv[1], '--apply' in sys.argv)
