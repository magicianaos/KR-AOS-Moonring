#!/usr/bin/env python3
"""빌드된 lua 에서 _T/_F/_D/_K 로 감싸이지 않은 영어 문장 리터럴을 찾는다."""
import os, re, sys
from collections import Counter

WRAP = re.compile(r'_[TFDK]\s*\(\s*$')
WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")


def scan(src):
    """yield (line, value, prefix)"""
    i, n, line = 0, len(src), 1
    while i < n:
        c = src[i]
        if c == '\n':
            line += 1; i += 1; continue
        if src.startswith('--', i):
            if src.startswith('--[[', i):
                j = src.find(']]', i)
                j = n if j < 0 else j + 2
            else:
                j = src.find('\n', i)
                j = n if j < 0 else j
            line += src.count('\n', i, j); i = j; continue
        if src.startswith('[[', i) or src.startswith('[==[', i):
            j = src.find(']]', i)
            j = n if j < 0 else j + 2
            line += src.count('\n', i, j); i = j; continue
        if c in '"\'':
            q, j, buf = c, i + 1, []
            while j < n:
                if src[j] == '\\':
                    buf.append(src[j:j+2]); j += 2; continue
                if src[j] == q:
                    j += 1; break
                if src[j] == '\n':
                    break
                buf.append(src[j]); j += 1
            yield line, ''.join(buf), src[max(0, i-14):i]
            line += src.count('\n', i, j); i = j; continue
        i += 1


def main(build):
    hits = []
    for fn in sorted(os.listdir(build)):
        if not fn.endswith('.lua') or fn == 'loc.lua':
            continue
        src = open(os.path.join(build, fn), encoding='utf-8', errors='replace').read()
        for line, val, pre in scan(src):
            if len(val) < 6 or len(WORD.findall(val)) < 2:
                continue
            if re.search(r'[ㄱ-힝]', val):
                continue
            if WRAP.search(pre.rstrip() + ('(' if pre.rstrip().endswith('(') else '')):
                continue
            if WRAP.search(pre):
                continue
            hits.append((fn, line, val))
    print('감싸이지 않은 영어 리터럴: %d' % len(hits))
    for f, c in Counter(h[0] for h in hits).most_common(25):
        print('%6d  %s' % (c, f))
    return hits


if __name__ == '__main__':
    hits = main(sys.argv[1] if len(sys.argv) > 1 else 'build')
    if '-v' in sys.argv:
        print()
        for f, l, v in hits:
            print('%s:%d  %s' % (f, l, v[:90]))
