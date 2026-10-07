#!/usr/bin/env python3
"""작업 찌꺼기를 정리한다.

지우는 것은 전부 **다시 만들어지는 것들**이다.
번역(ko.csv)·폰트·스크립트·배포 최신본은 건드리지 않는다.
"""

import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 툴킷 안에서 지워도 되는 것 (적용.bat 이 다시 만든다)
TEMP_DIRS = [
    ('src',                  '원본 게임 소스 (적용.bat 이 exe 에서 다시 풂)'),
    ('build',                '패치된 소스 (적용.bat 이 다시 만듦)'),
    ('dist',                 '배포 zip 작업 폴더 (배포만들기.bat 이 다시 만듦)'),
    (os.path.join('tools', '__pycache__'), '파이썬 캐시'),
]

VER_RE = re.compile(r'^Moonring_한글패치_v(\d+(?:\.\d+)*)(?:\.zip)?$')


def human(n):
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return '%.0f %s' % (n, u)
        n /= 1024.0
    return '%.1f TB' % n


def dir_size(p):
    total = 0
    for dp, _dn, fns in os.walk(p):
        for fn in fns:
            try:
                total += os.path.getsize(os.path.join(dp, fn))
            except OSError:
                pass
    return total


def vkey(s):
    return tuple(int(x) for x in s.split('.'))


def plan_dist(dist_dir):
    """배포 폴더에서 최신 버전만 남기고 나머지를 지울 목록을 만든다."""
    if not os.path.isdir(dist_dir):
        return [], None
    found = {}
    for name in os.listdir(dist_dir):
        m = VER_RE.match(name)
        if m:
            found.setdefault(m.group(1), []).append(name)
    if not found:
        return [], None
    newest = max(found, key=vkey)
    out = []
    for ver, names in found.items():
        if ver == newest:
            # 같은 버전이라도 압축을 푼 폴더는 지운다 (zip 만 남김)
            for n in names:
                if not n.endswith('.zip'):
                    out.append(os.path.join(dist_dir, n))
            continue
        for n in names:
            out.append(os.path.join(dist_dir, n))
    return sorted(out), newest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dist', default=os.path.join(ROOT, '..', '배포'),
                    help='배포본을 모아 둔 폴더')
    ap.add_argument('--game', default=None, help='게임 폴더 (생략하면 자동 탐색)')
    ap.add_argument('--yes', action='store_true', help='묻지 않고 바로 지움')
    a = ap.parse_args()

    targets = []   # (경로, 설명, 크기)

    for rel, why in TEMP_DIRS:
        p = os.path.join(ROOT, rel)
        if os.path.isdir(p):
            targets.append((p, why, dir_size(p)))

    dist_dir = os.path.abspath(a.dist)
    dist_targets, newest = plan_dist(dist_dir)
    for p in dist_targets:
        why = '옛 배포본' if os.path.isfile(p) else '압축 푼 배포본'
        size = os.path.getsize(p) if os.path.isfile(p) else dir_size(p)
        targets.append((p, why, size))

    # 게임 폴더의 미번역 보고 파일 (게임이 다시 만든다)
    try:
        sys.path.insert(0, HERE)
        import mrloc
        game = mrloc.find_game(a.game, interactive=False)
        miss = os.path.join(game, 'lang', 'ko_missing.csv')
        if os.path.isfile(miss):
            targets.append((miss, '미번역 보고 파일 (게임이 다시 만듦)',
                            os.path.getsize(miss)))
    except SystemExit:
        pass

    if not targets:
        print('지울 것이 없습니다. 이미 깔끔합니다.')
        return

    total = sum(t[2] for t in targets)
    print()
    print('지울 목록')
    print('-' * 62)
    for p, why, size in targets:
        print('  %-9s  %s' % (human(size), os.path.relpath(p, ROOT)))
        print('             %s' % why)
    print('-' * 62)
    print('  합계 %s' % human(total))
    if newest:
        print('  배포본은 v%s 만 남깁니다.' % newest)
    print()
    print('번역(ko.csv)·폰트·스크립트·원본 백업(.bak)은 지우지 않습니다.')
    print()

    if not a.yes:
        try:
            if input('진행할까요? (y/N): ').strip().lower() != 'y':
                print('취소했습니다.')
                return
        except (EOFError, KeyboardInterrupt):
            print('취소했습니다.')
            return

    freed = 0
    for p, _why, size in targets:
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
            freed += size
            print('  지움: %s' % os.path.relpath(p, ROOT))
        except OSError as e:
            print('  [!] 실패: %s (%s)' % (os.path.relpath(p, ROOT), e))

    print()
    print('완료. %s 를 확보했습니다.' % human(freed))
    print('src / build 는 다음에 적용.bat 을 돌리면 다시 만들어집니다.')


if __name__ == '__main__':
    main()
