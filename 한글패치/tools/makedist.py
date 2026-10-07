#!/usr/bin/env python3
"""배포용 패키지를 만든다.

원본 exe 안의 파일과 패치된 build/ 를 비교해 **바뀐 파일만** 골라내고,
파이썬 없이 돌아가는 PowerShell 적용기와 안내문을 함께 묶는다.
"""

import argparse
import hashlib
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_TPL = os.path.join(ROOT, 'dist_src')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read_tree(root):
    out = {}
    for dp, _dn, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            out[os.path.relpath(p, root).replace('\\', '/')] = p
    return out


def original_files(exe, tmpdir):
    """원본 exe 안의 파일을 풀어 {rel: path} 로 돌려준다."""
    with zipfile.ZipFile(exe) as z:
        z.extractall(tmpdir)
    return read_tree(tmpdir)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # 메모장에서 깨지지 않도록 BOM + CRLF
    with open(path, 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write(text)


def game_build(src):
    p = os.path.join(src, 'build_number.txt')
    if os.path.isfile(p):
        return open(p, encoding='utf-8', errors='replace').readline().strip()
    return 'unknown'


def rebuild(a, exe):
    """원본 exe 를 풀고 -> 문자열 추출(번역 유지) -> 패치 까지 한 번에."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import argparse as _ap
    import mrloc

    lang = a.lang or os.path.join(a.game, 'lang', 'ko.csv')
    if not os.path.isfile(lang):
        lang = os.path.join(ROOT, 'lang', 'ko.csv')
    print('번역 파일   : %s' % lang)

    ns = _ap.Namespace(cmd='patch', exe=exe, src=a.src, build=a.build,
                       lang=lang, out=None, verbose=False, limit=30,
                       game=a.game, replace=False, push_lang=False)
    print('원본 풀기...')
    mrloc.cmd_unpack(ns)
    print('문자열 추출...')
    mrloc.cmd_extract(ns)
    print('패치...')
    mrloc.cmd_patch(ns)
    # 툴킷 쪽 사본도 최신으로
    master = os.path.join(ROOT, 'lang', 'ko.csv')
    if os.path.abspath(master) != os.path.abspath(lang):
        shutil.copy(lang, master)
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default=None,
                    help='Moonring.exe 가 있는 폴더 (생략하면 자동 탐색)')
    ap.add_argument('--build', default=os.path.join(ROOT, 'build'))
    ap.add_argument('--src', default=os.path.join(ROOT, 'src'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'dist'))
    ap.add_argument('--version', default='1.0')
    ap.add_argument('--rebuild', action='store_true',
                    help='원본 exe 를 풀고 최신 번역으로 다시 패치한 뒤 포장')
    ap.add_argument('--lang', default=None,
                    help='번역 원본 csv (기본: 게임 폴더의 lang/ko.csv)')
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import mrloc
    a.game = mrloc.find_game(a.game)
    print('게임 폴더   : %s' % a.game)

    exe = os.path.join(a.game, 'Moonring.exe.bak')
    if not os.path.isfile(exe):
        exe = os.path.join(a.game, 'Moonring.exe')
    if not os.path.isfile(exe):
        sys.exit('원본 exe 를 찾을 수 없습니다: %s' % a.game)
    if a.rebuild:
        rebuild(a, exe)

    if not os.path.isdir(a.build):
        sys.exit('패치 결과가 없습니다. --rebuild 를 붙이거나 mrloc.py patch 를 먼저 '
                 '실행하세요: %s' % a.build)

    print('원본 exe   : %s' % exe)
    src_hash = sha256(exe)
    print('SHA-256    : %s' % src_hash)

    import tempfile
    tmp = tempfile.mkdtemp(prefix='mrdist_')
    try:
        orig = original_files(exe, tmp)
        built = read_tree(a.build)

        payload = []
        for rel in sorted(built):
            op = orig.get(rel)
            if op is None:
                payload.append((rel, built[rel], 'new'))
                continue
            if open(op, 'rb').read() != open(built[rel], 'rb').read():
                payload.append((rel, built[rel], 'mod'))
        gone = sorted(set(orig) - set(built))
        if gone:
            print('경고: 원본에만 있는 파일 %d개 (패치는 파일을 지우지 않습니다)' % len(gone))

        name = 'Moonring_한글패치_v%s' % a.version
        outdir = os.path.join(a.out, name)
        if os.path.isdir(outdir):
            shutil.rmtree(outdir)
        os.makedirs(outdir)

        # 1) 교체 파일
        total = 0
        for rel, p, _kind in payload:
            dst = os.path.join(outdir, 'patch', *rel.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(p, dst)
            total += os.path.getsize(p)

        # 2) 적용기 / 안내문 / 라이선스
        gb = game_build(a.src)
        for rel, p in sorted(read_tree(SRC_TPL).items()):
            dst = os.path.join(outdir, *rel.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if rel.endswith('.txt'):
                text = open(p, encoding='utf-8').read()
                text = (text.replace('{{VERSION}}', a.version)
                            .replace('{{GAMEBUILD}}', gb))
                write_text(dst, text)
            elif rel.endswith('.ps1'):
                # PowerShell 5.1 은 BOM 이 없으면 ANSI 로 읽어 한글이 깨진다
                write_text(dst, open(p, encoding='utf-8').read())
            else:
                shutil.copy2(p, dst)

        # 3) manifest (기계가 읽으므로 BOM 없이)
        with open(os.path.join(outdir, 'manifest.txt'), 'w',
                  encoding='utf-8', newline='\r\n') as _mf:
            _mf.write(
                   'patch_version=%s\n'
                   'game_build=%s\n'
                   'source_sha256=%s\n'
                   'file_count=%d\n'
                   % (a.version, gb, src_hash, len(payload)))

        # 4) zip
        zpath = os.path.join(a.out, name + '.zip')
        if os.path.isfile(zpath):
            os.remove(zpath)
        with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for dp, _dn, fns in os.walk(outdir):
                for fn in sorted(fns):
                    p = os.path.join(dp, fn)
                    arc = os.path.join(name, os.path.relpath(p, outdir))
                    z.write(p, arc.replace('\\', '/'))

        print()
        print('교체 파일   : %d개 (%.1f MB)' % (len(payload), total / 1e6))
        print('  새 파일   : %d' % sum(1 for _r, _p, k in payload if k == 'new'))
        print('  수정 파일 : %d' % sum(1 for _r, _p, k in payload if k == 'mod'))
        print('폴더        : %s' % outdir)
        print('배포 zip    : %s  (%.1f MB)' % (zpath, os.path.getsize(zpath) / 1e6))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
