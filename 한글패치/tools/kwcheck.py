#!/usr/bin/env python3
"""Reproduces the game's dialogue-keyword discovery to make sure every english
keyword the player must be able to TYPE still appears in the korean text.

speech_area.lua highlights, for each (location, speaker), that speaker's own
keywords wherever they occur as whole words inside dialogueSet / summary.
Only keywords actually found there become learnable.  If a keyword survives in
english but the translation dropped it, that conversation branch is lost.
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# same boundary class the patched tools.replaceString uses
B = r"\s,.?!;:\-()\[\]<>'\"/\\|*+&=~`#$@-\U0010ffff"


def whole_word(text, kw):
    pat = r"(?:(?<=[" + B + r"])|^)" + re.escape(kw) + r"(?=[" + B + r"]|$)"
    return re.search(pat, text) is not None


DIALOGUE_REL = 'data/DialogueData - Sheet1.csv'


def load_dialogue(src):
    """src/ 가 있으면 거기서, 없으면 게임 exe 안에서 바로 꺼내 읽는다."""
    p = os.path.join(src, *DIALOGUE_REL.split('/'))
    if os.path.isfile(p):
        with open(p, newline='', encoding='utf-8', errors='replace') as f:
            return list(csv.DictReader(f))

    # src/ 를 지웠을 때를 대비해 exe(zip) 에서 직접 꺼낸다
    import io
    import zipfile
    sys.path.insert(0, HERE)
    import mrloc
    game = mrloc.find_game(None)
    exe = os.path.join(game, 'Moonring.exe.bak')
    if not os.path.isfile(exe):
        exe = os.path.join(game, 'Moonring.exe')
    with zipfile.ZipFile(exe) as z:
        raw = z.read(DIALOGUE_REL)
    text = raw.decode('utf-8', errors='replace')
    return list(csv.DictReader(io.StringIO(text, newline='')))


def load_lang(lang):
    tr = {}
    with open(lang, newline='', encoding='utf-8-sig') as f:
        for r in csv.reader(f):
            if len(r) >= 4 and r[0] == 'S' and r[3]:
                tr[r[2]] = r[3]
    return tr


def clean(v):
    """what csvLoader leaves in the table for a text field"""
    v = (v or '').replace('’', "'").replace('\r', '')
    if v in ('', 'NA'):
        return None
    if ';' in v or '::' in v:
        return None
    return v.strip()


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'src')
    lang = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'lang', 'ko.csv')
    rows = load_dialogue(src)
    tr = load_lang(lang)

    # keywords per (location, speaker)
    kws = {}
    for r in rows:
        k = clean(r.get('keyword'))
        if k:
            kws.setdefault((r['location'], r['speaker']), set()).add(k)

    problems = []
    checked = found_total = 0
    for r in rows:
        key = (r['location'], r['speaker'])
        speaker_kws = kws.get(key, set())
        if not speaker_kws:
            continue
        for field in ('dialogueSet', 'summary'):
            en = clean(r.get(field))
            if not en:
                continue
            ko = tr.get(en)
            if not ko:
                continue
            checked += 1
            missing = []
            for kw in speaker_kws:
                if whole_word(en, kw):
                    found_total += 1
                    if not whole_word(ko, kw):
                        missing.append(kw)
            if missing:
                problems.append({'id': r.get('') or r.get('I\'m sure ') or '?',
                                 'location': r['location'], 'speaker': r['speaker'],
                                 'field': field, 'en': en, 'ko': ko,
                                 'missing': sorted(missing)})
    print('검사한 대사 %d개 / 키워드 등장 %d회 / 문제 %d건'
          % (checked, found_total, len(problems)))
    if problems and '--json' in sys.argv:
        import json
        out = os.path.join(ROOT, 'tr', 'kw_problems.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(problems, f, ensure_ascii=False, indent=1)
        print('->', out)
    else:
        for p in problems[:20]:
            print('  [%s/%s %s] 빠진 키워드: %s' % (p['location'], p['speaker'],
                                                p['field'], ', '.join(p['missing'])))
            print('     en: %s' % p['en'][:110])
            print('     ko: %s' % p['ko'][:110])
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
