#!/usr/bin/env python3
"""
mrloc.py - Moonring Korean localisation toolchain.

  unpack   : Moonring.exe            -> src/            (original game files)
  extract  : src/                    -> lang/ko.csv     (merges, keeps existing ko)
  patch    : src/ + lang/ko.csv      -> build/          (localised game files)
  repack   : build/ + Moonring.exe   -> Moonring_KO.exe

Typical use after a game update:
  python mrloc.py unpack  --exe Moonring.exe
  python mrloc.py extract
  python mrloc.py patch
  python mrloc.py repack  --exe Moonring.exe --out Moonring_KO.exe
"""

import argparse
import csv
import os
import re
import shutil
import tempfile
import struct
import sys
import zipfile
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lualex import (match_bracket, split_top_level, parse_string_literal,
                    lua_quote, iter_code_spans, skip_atom)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SKIP_DIRS = ('library/', 'redist/', 'assets/', 'music/', 'shaders/', 'generated/')
SKIP_FILES = {
    'loc.lua', 'prof.lua', 'console.lua', 'sfxr_edit.lua', 'state_editor.lua',
    'ide_colour_picker.lua', 'filesystem_debug.lua', 'BUILD_sfxr.lua',
}

# ---------------------------------------------------------------- sink table
# method name -> argument indices (1-based) that hold player-visible text
METHOD_SINKS = {
    'addText':               [1],
    'openAlertBox':          [1],
    'showDelayedAlertBox':   [1],
    'setDeathCauseString':   [1],
    'animalCrossingSpeech':  [1],
    'openTextInputBox':      [1],
    'say':                   [1, 2],
    'showIgnoranceText':     [1],
    'addTutorialText':       [1],
    'addRisingTextToActorWithID': [2],
    'openConfirmBox':        [1, 2, 3],
    'openNumberBox':         [1],
    'alterText':             [1],
    'printEnterDetails':     [1, 5],
    'sayWithoutQuotes':      [1],
    'printStatAsPercentage': [1],
    'printDamageStat':       [1],
    'printSlashStat':        [1],
}
# fully qualified function -> arg indices
FUNC_SINKS = {
    'love.graphics.print':    [1],
    'love.graphics.printf':   [1],
    'tools.drawOutlinedText': [1],
    'tools.drawFormattedOutlinedText': [1],
    'tools.printTwoThings':   [1, 2],
    'string.format':          [1],
}
# receiver-name keyword -> (method, arg indices)
RECEIVER_SINKS = [
    ('alertbox',       'setActive', [1]),
    ('multichoicebox', 'setActive', [2, 3]),
    ('confirmbox',     'setActive', [1, 2, 3]),
    ('slowtextdrawer', 'setText',   [1]),
]

# table fields whose literal values are display text, in EVERY file
GLOBAL_FIELD_SINKS = ['text']

# assignments to these variable names hold display text (sentence required)
ASSIGN_VARS = [r'str\d*', r'msg\d*', r'message\d*', 'title', 'label',
               'desc', 'description', 'tooltip', r'line\d*', 'caption',
               'prompt', r'text\d*', 'blurb', 'header']

# files where ANY  x = "literal"  assignment is display text
# only wrap  x = "literal"  on lines matching this pattern, for these files
RHS_LINE_GUARD = {'globals.lua': re.compile(r'useStrings\[|hengeToDescription\[')}

RHS_ASSIGN_FILES = {
    'globals.lua': True,
    'economy.lua': True,          # value = allow single words
    'character_panel.lua': False, 'inventory_panel.lua': False,
    'buy_panel.lua': False, 'sell_panel.lua': False, 'note_panel.lua': False,
    'state_game_gui.lua': False, 'skill_tree.lua': False,
    'speech_area.lua': False, 'tutorial_box.lua': False,
}

# files where any long sentence literal is display text
LONGTEXT_FILES = {'help.lua': 18, 'speech_area.lua': 22, 'cell_data.lua': 22,
                  'world_data.lua': 18, 'skill_tree.lua': 18}

# never treat literals on these lines as display text
NOISE_ASSIGN_TARGETS = ('G_PreRandomFunctionName', 'G_LogName', 'LOG_NAME')

NOISE_CALL_RE = re.compile(r'(?<![\w.])(assert|error|LogInfo|LogError|LogWarning|print|tools\.log|tools\.printTwoThings|require|love\.filesystem|love\.graphics\.newFont|love\.graphics\.newImageFont|newShader|:setFilter)\s*\(')

# file -> table field names whose literal values are display text
FIELD_SINKS = {
    'achievements.lua':      ['text'],
    'world_data.lua':        ['overworldRegionName', 'displayName', 'longName'],
    'state_title_screen.lua': ['text'],
    'state_game.lua':        ['text'],
    'skill_tree.lua':        ['name', 'description', 'flavour'],
    'tutorials.lua':         ['text', 'title', 'joystickText'],
    'economy.lua':           ['name', 'displayName'],
    'help.lua':              ['text', 'title'],
    'note_panel.lua':        ['text'],
    'calendar.lua':          ['name'],
    'globals.lua':           ['restrictions', 'stat', 'boon', 'shortStat', 'name', 'noun'],
}

# plain string arrays that are display text but look like identifiers
EXTRA_TABLE_SCAN = {
    'globals.lua': ['stupidCreatureNames', 'traderMadTextArray',
                    'traderHateTextArray', 'madnessStrings',
                    'hengeToDescription'],
    'state_game.lua': ['gKeyAdjectives', 'gKeyMaterials',
                       'gHerbAdjectives', 'gHerbMaterials'],
}

# some field names are only display text on certain lines of a file
FIELD_LINE_GUARD = {
    ('globals.lua', 'name'): re.compile(r'godData|gasTrapTypeData'),
}

BLOCK_VALUES = {
    'NA', 'TRUE', 'FALSE', 'nil', 'true', 'false', 'NULL', 'no_data',
}
PATH_RE = re.compile(r'^[\w /\-]+\.(png|lua|csv|txt|fs|ttf|otf|wav|ogg|xm|it)$', re.I)
TAG_RE = re.compile(r'\{[a-zA-Z0-9_]+\}')
CALL_RE = re.compile(r'(?<![\w.:])([A-Za-z_]\w*(?:[.:]\w+)*)\s*\(')


def strip_tags(s):
    return TAG_RE.sub('', s)


def translatable(s, allow_single_word=True):
    if not s or s in BLOCK_VALUES:
        return False
    if PATH_RE.match(s):
        return False
    core = strip_tags(s).replace('\\n', ' ').strip()
    if not re.search(r'[A-Za-z]', core):
        return False
    if len(core) < 2:
        return False
    if not allow_single_word and ' ' not in core.strip():
        return False
    # obvious code-ish identifiers
    if re.fullmatch(r'[a-z_]+[A-Za-z0-9_]*', core) and ' ' not in core and len(core) < 4:
        return False
    return True


# ---------------------------------------------------------------- rewriting
class Rewriter:
    def __init__(self, path, text):
        self.path = path
        self.text = text
        self.edits = []          # (start, end, replacement)
        self.msgids = []         # (msgid, context)

    def add_edit(self, start, end, repl):
        for s, e, _ in self.edits:
            if not (end <= s or start >= e):
                return False
        self.edits.append((start, end, repl))
        return True

    def record(self, msgid, ctx):
        self.msgids.append((msgid, ctx))

    def apply(self):
        if not self.edits:
            return self.text
        out, last = [], 0
        for s, e, repl in sorted(self.edits):
            out.append(self.text[last:s])
            out.append(repl)
            last = e
        out.append(self.text[last:])
        return ''.join(out)


def line_of(text, idx):
    return text.count('\n', 0, idx) + 1



KEYWORD_STOP = ('end', 'else', 'elseif', 'then', 'do', 'until', 'return',
                'local', 'if', 'for', 'while', 'repeat', 'function', 'break', 'goto')


def rhs_extent(text, start, limit):
    """Length of the expression starting at `start`, stopping at a top-level
    comma / closing bracket / lua keyword / comment / end of line."""
    depth = 0
    i = start
    while i < limit:
        c = text[i]
        if c in '"\'':
            i = skip_atom(text, i)
            continue
        if c == '-' and text.startswith('--', i):
            break
        if c in '([{':
            depth += 1
            i += 1
            continue
        if c in ')]}':
            if depth == 0:
                break
            depth -= 1
            i += 1
            continue
        if depth == 0:
            if c == ',' or c == ';':
                break
            if c.isalpha() or c == '_':
                j = i
                while j < limit and (text[j].isalnum() or text[j] == '_'):
                    j += 1
                word = text[i:j]
                prev = text[i - 1] if i > start else ' '
                if word in KEYWORD_STOP and prev not in '._:':
                    break
                i = j
                continue
        i += 1
    return i - start


def transform_arg(arg, rw, ctx, allow_single_word=True, allow_letterless=False):
    """Return replacement text for one call argument, or None."""
    chain = split_top_level(arg, '..')
    parsed = [parse_string_literal(p) for p in chain]

    # merge consecutive literals, non-literals become placeholders
    fmt_parts, args, idx = [], [], 0
    has_literal = False
    for p, lit in zip(chain, parsed):
        if lit is not None:
            fmt_parts.append(lit[0])
            has_literal = True
        else:
            expr = p.strip()
            if not expr:
                return None
            idx += 1
            if idx > 9:
                return None
            fmt_parts.append('%%%d' % idx)
            args.append(expr)
    if not has_literal:
        return secondary_pass(arg, rw, ctx)

    fmt = ''.join(fmt_parts)
    # the literal part must actually carry words
    letters = re.sub(r'%\d', '', fmt)
    if not translatable(letters, allow_single_word):
        # a display sink with no words but with values - still route it through
        # _D so the VALUES get translated (" < " .. category .. " > ")
        if allow_letterless and args:
            return '_D(%s, %s)' % (lua_quote(fmt), ', '.join(args))
        return secondary_pass(arg, rw, ctx) if args else None

    rw.record(fmt, ctx)
    if not args:
        return '_T(%s)' % lua_quote(fmt)
    return '_F(%s, %s)' % (lua_quote(fmt), ', '.join(args))


def secondary_pass(arg, rw, ctx):
    """Wrap sentence-like literals found *inside* a sink argument expression."""
    edits = []
    i, n = 0, len(arg)
    while i < n:
        c = arg[i]
        if c in '"\'':
            end = skip_atom(arg, i)
            lit = parse_string_literal(arg[i:end])
            if lit is not None:
                before = arg[:i].rstrip()
                after = arg[end:].lstrip()
                is_key = before.endswith('[') or after.startswith(']')
                if not is_key and translatable(lit[0], allow_single_word=False):
                    rw.record(lit[0], ctx)
                    edits.append((i, end, '_T(%s)' % lua_quote(lit[0])))
            i = end
            continue
        i += 1
    if not edits:
        return None
    out, last = [], 0
    for s, e, r in edits:
        out.append(arg[last:s])
        out.append(r)
        last = e
    out.append(arg[last:])
    return ''.join(out)


def sink_for(callee):
    """callee like 'self.game:addText' -> (arg indices) or None"""
    if callee in FUNC_SINKS:
        return FUNC_SINKS[callee]
    m = re.search(r'[.:](\w+)$', callee)
    name = m.group(1) if m else callee
    recv = callee[:m.start()].lower() if m else ''
    for key, meth, idxs in RECEIVER_SINKS:
        if name == meth and key in recv:
            return idxs
    if name in METHOD_SINKS and (m and m.group(0)[0] == ':'):
        return METHOD_SINKS[name]
    if callee in METHOD_SINKS:
        return METHOD_SINKS[callee]
    return None



# ---------------------------------------------------------- wide UI scan
# Anything drawn through love.graphics.print/printf is translated at runtime
# by a hook in loc.lua, so these strings only need to EXIST in ko.csv - the
# source is never modified, which keeps label comparisons (== "Show Help")
# working.
UI_SKIP_FILES = {'sfxr_edit.lua', 'prof.lua', 'console.lua', 'state_editor.lua',
                 'ide_colour_picker.lua', 'filesystem_debug.lua', 'trigger_data.lua',
                 'music_downloader.lua', 'markov_names.lua', 'sound_list.lua',
                 'all_tiles.lua', 'colour_list.lua', 'particle_data.lua',
                 'doll_data.lua', 'dungeon_data.lua', 'dungeon_biomes.lua',
                 'arena_data.lua', 'geometric_effects.lua',
                 'treasure_sets.lua', 'turret_sets.lua', 'creature_group_set_data.lua',
                 'overworld_area_data.lua', 'ruins.lua', 'dungeon_chunks.lua',
                 'dungeon_gen_base.lua', 'dungeon_masks.lua', 'maze_snake.lua',
                 'mazegen.lua', 'maze_base.lua', 'texture_packer.lua'}

UI_NOISE = re.compile(r'(?<![\w.])(assert|error|LogInfo|LogError|LogWarning|print|'
                      r'tools\.log|require|G_playSound|G_playSFXRSound|newImageFont|'
                      r'newShader|newFont|newImage|setFilter|getInfo|love\.filesystem|'
                      r'io\.open|os\.|hasProperty|setProperty|getProperty|'
                      r'isKeyPressed|keyboard\.|:getInfo)\s*[(.\[]')


def ui_display(s):
    if not s or len(s) < 2:
        return False
    if not re.search(r'[A-Za-z]', s):
        return False
    if PATH_RE.match(s) or s in BLOCK_VALUES:
        return False
    core = strip_tags(s).replace('\\n', ' ').strip()
    if not core or not re.search(r'[A-Za-z]', core):
        return False
    if re.fullmatch(r'[a-z][a-zA-Z0-9]*', core):        # camelCase / lowercase id
        return False
    if re.fullmatch(r'[a-zA-Z0-9_\-]+', core) and '_' in core:
        return False                                    # snake_case / kebab id
    if re.fullmatch(r'[A-Z0-9_]+', core):               # CONSTANT
        return False
    if ' ' in core:
        return True
    if core[0].isupper():
        return True
    if core.endswith(':') or core.endswith('%'):
        return True
    return False


def scan_ui_literals(relpath, text, rw, covered):
    fname = os.path.basename(relpath)
    if fname in UI_SKIP_FILES:
        return
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '-' and text.startswith('--', i):
            i = skip_atom(text, i)
            continue
        if c == '[' and text.startswith('[[', i):
            i = skip_atom(text, i)
            continue
        if c in '"\'':
            end = skip_atom(text, i)
            if not any(s <= i < e for s, e in covered):
                lit = parse_string_literal(text[i:end])
                if lit is not None and ui_display(lit[0]):
                    before = text[:i].rstrip()
                    after = text[end:].lstrip()
                    if not before.endswith('[') and not after.startswith(']'):
                        ls = text.rfind('\n', 0, i) + 1
                        le = text.find('\n', i)
                        le = len(text) if le < 0 else le
                        if not UI_NOISE.search(text[ls:le]):
                            rw.record(lit[0], 'ui:%s:%d' % (relpath, line_of(text, i)))
            i = end
            continue
        i += 1


def process_lua(relpath, text):
    rw = Rewriter(relpath, text)
    fname = os.path.basename(relpath)
    code_spans = list(iter_code_spans(text))

    def in_code(pos):
        for s, e in code_spans:
            if s <= pos < e:
                return True
        return False

    # ---- 1. sink calls
    covered = []
    for m in CALL_RE.finditer(text):
        if not in_code(m.start()):
            continue
        if any(s <= m.start() < e for s, e in covered):
            continue
        idxs = sink_for(m.group(1))
        if not idxs:
            continue
        open_idx = m.end() - 1
        close_idx = match_bracket(text, open_idx)
        if close_idx < 0:
            continue
        inner = text[open_idx + 1:close_idx]
        args = split_top_level(inner, ',')
        ctx = '%s:%d' % (relpath, line_of(text, m.start()))
        newargs, changed = [], False
        for k, a in enumerate(args, 1):
            if k in idxs:
                # a table constructor of choices -> handle each literal
                if a.strip().startswith('{'):
                    r = secondary_pass(a, rw, ctx)
                else:
                    r = transform_arg(a, rw, ctx, allow_letterless=True)
                if r is not None:
                    lead = a[:len(a) - len(a.lstrip())]
                    newargs.append(lead + r)
                    changed = True
                    continue
            newargs.append(a)
        if changed:
            repl = ','.join(newargs)
            if rw.add_edit(open_idx + 1, close_idx, repl):
                covered.append((open_idx, close_idx))

    # ---- 2. table fields  (text = "..." .. x .. "...")
    for field in FIELD_SINKS.get(fname, []) + GLOBAL_FIELD_SINKS:
        for m in re.finditer(r'(?<![\w.])' + field + r'\s*=\s*(?=["\'])', text):
            if not in_code(m.start()):
                continue
            if any(s <= m.start() < e for s, e in covered):
                continue
            line_end = text.find('\n', m.end())
            line_end = len(text) if line_end < 0 else line_end
            ext = rhs_extent(text, m.end(), line_end)
            rhs = text[m.end():m.end() + ext].rstrip()
            ext = len(rhs)
            if not rhs:
                continue
            guard = FIELD_LINE_GUARD.get((fname, field))
            if guard is not None:
                ls = text.rfind('\n', 0, m.start()) + 1
                if not guard.search(text[ls:line_end]):
                    continue
            ctx = '%s:%d' % (relpath, line_of(text, m.start()))
            r = transform_arg(rhs, rw, ctx)
            if r is not None and rw.add_edit(m.end(), m.end() + ext, r):
                covered.append((m.end(), m.end() + ext))

    # ---- 3. assignments to display-ish variables:  str = "..." .. x .. "..."
    rhs_any = fname in RHS_ASSIGN_FILES
    names = (r'[\w\.]*\[[^\]]*\]|[\w\.]+' if rhs_any
             else r'(?:[\w.]+\.)?(?:' + '|'.join(ASSIGN_VARS) + r')')
    assign_re = re.compile(r'(?<![\w.])(?:local\s+)?(' + names + r')\s*=\s*(?=["\'])')
    for m in assign_re.finditer(text):
        if not in_code(m.start()):
            continue
        if any(s2 <= m.start() < e2 for s2, e2 in covered):
            continue
        line_start = text.rfind('\n', 0, m.start()) + 1
        line_end = text.find('\n', m.end())
        line_end = len(text) if line_end < 0 else line_end
        line = text[line_start:line_end]
        if NOISE_CALL_RE.search(line):
            continue
        if any(t in line for t in NOISE_ASSIGN_TARGETS):
            continue
        lg = RHS_LINE_GUARD.get(fname)
        if lg is not None and not lg.search(line):
            continue
        # 내부 식별자 리맵은 건드리면 안 된다:
        #   if world_name == "Zoom" then world_name = "Overworld" end
        # 여기서 "Overworld" 를 번역하면 테이블 키가 어긋나 크래시가 난다.
        # 비교 대상과 대입 대상이 같은 변수일 때만 걸러내므로
        #   if str == "name" then rand = "I am ..." end
        # 같은 진짜 표시 문구는 그대로 번역된다.
        var = m.group(1)
        if var and re.search(r'(?<![\w.])if\s+' + re.escape(var)
                             + r'\s*==\s*["\']', line):
            continue
        # take the rhs expression, stopping at a top-level keyword/bracket
        ext = rhs_extent(text, m.end(), line_end)
        rhs = text[m.end():m.end() + ext].rstrip()
        ext = len(rhs)
        if not rhs:
            continue
        r = transform_arg(rhs, rw, '%s:%d' % (relpath, line_of(text, m.start())),
                          allow_single_word=RHS_ASSIGN_FILES.get(fname, False))
        if r is not None:
            if rw.add_edit(m.end(), m.end() + ext, r):
                covered.append((m.end(), m.end() + ext))

    # ---- 3b. accumulation:  str = str .. "..." .. x   /   tab.str = tab.str .. "..."
    acc_names = (r'[\w\.]*\[[^\]]*\]|[\w\.]+' if rhs_any
                 else r'(?:[\w.]+\.)?(?:' + '|'.join(ASSIGN_VARS) + r')')
    acc_re = re.compile(r'(?<![\w.])(' + acc_names + r')\s*=\s*\1\s*\.\.\s*(?=["\'])')
    for m in acc_re.finditer(text):
        if not in_code(m.start()):
            continue
        if any(s2 <= m.start() < e2 for s2, e2 in covered):
            continue
        target = m.group(1)
        if not re.search(r'(?:^|\.)(?:' + '|'.join(ASSIGN_VARS) + r')$', target):
            continue
        line_start = text.rfind('\n', 0, m.start()) + 1
        line_end = text.find('\n', m.end())
        line_end = len(text) if line_end < 0 else line_end
        line = text[line_start:line_end]
        if NOISE_CALL_RE.search(line):
            continue
        if any(t in line for t in NOISE_ASSIGN_TARGETS):
            continue
        ext = rhs_extent(text, m.end(), line_end)
        rhs = text[m.end():m.end() + ext].rstrip()
        ext = len(rhs)
        if not rhs:
            continue
        r = transform_arg(rhs, rw, '%s:%d' % (relpath, line_of(text, m.start())))
        if r is not None and rw.add_edit(m.end(), m.end() + ext, r):
            covered.append((m.end(), m.end() + ext))

    # ---- 3c.  local str = something .. "..." .. x     (표시용 변수 이름만)
    var_re = re.compile(r'(?<![\w.])(?:local\s+)?(?:[\w.]+\.)?(?:'
                        + '|'.join(ASSIGN_VARS) + r')\s*=\s*(?!["\'])(?=[\w({])')
    for m in var_re.finditer(text):
        if not in_code(m.start()):
            continue
        if any(s2 <= m.start() < e2 for s2, e2 in covered):
            continue
        line_start = text.rfind('\n', 0, m.start()) + 1
        line_end = text.find('\n', m.end())
        line_end = len(text) if line_end < 0 else line_end
        line = text[line_start:line_end]
        if NOISE_CALL_RE.search(line) or '"' not in line and "'" not in line:
            continue
        if any(t in line for t in NOISE_ASSIGN_TARGETS):
            continue
        ext = rhs_extent(text, m.end(), line_end)
        rhs = text[m.end():m.end() + ext].rstrip()
        ext = len(rhs)
        if not rhs or '..' not in rhs or ('"' not in rhs and "'" not in rhs):
            continue
        r = transform_arg(rhs, rw, '%s:%d' % (relpath, line_of(text, m.start())))
        if r is not None and rw.add_edit(m.end(), m.end() + ext, r):
            covered.append((m.end(), m.end() + ext))

    # ---- 3d.  return "문장 " .. x .. " 나머지"
    ret_re = re.compile(r'(?<![\w.])return\s+(?=["\'])')
    for m in ret_re.finditer(text):
        if not in_code(m.start()):
            continue
        if any(s2 <= m.start() < e2 for s2, e2 in covered):
            continue
        line_start = text.rfind('\n', 0, m.start()) + 1
        line_end = text.find('\n', m.end())
        line_end = len(text) if line_end < 0 else line_end
        line = text[line_start:line_end]
        if NOISE_CALL_RE.search(line):
            continue
        ext = rhs_extent(text, m.end(), line_end)
        rhs = text[m.end():m.end() + ext].rstrip()
        ext = len(rhs)
        if not rhs or '..' not in rhs:
            continue
        r = transform_arg(rhs, rw, '%s:%d' % (relpath, line_of(text, m.start())))
        if r is not None and rw.add_edit(m.end(), m.end() + ext, r):
            covered.append((m.end(), m.end() + ext))

    # ---- 4. long sentence literals in text-heavy data files
    minlen = LONGTEXT_FILES.get(fname)
    if minlen:
        i, n = 0, len(text)
        while i < n:
            c = text[i]
            if c == '-' and text.startswith('--', i):
                i = skip_atom(text, i)
                continue
            if c == '[' and text.startswith('[[', i):
                i = skip_atom(text, i)
                continue
            if c in '"\'':
                end = skip_atom(text, i)
                if not any(s2 <= i < e2 for s2, e2 in covered):
                    lit = parse_string_literal(text[i:end])
                    if lit is not None and len(lit[0]) >= minlen and translatable(lit[0], False):
                        line_start = text.rfind('\n', 0, i) + 1
                        line_end = text.find('\n', i)
                        line_end = len(text) if line_end < 0 else line_end
                        if not NOISE_CALL_RE.search(text[line_start:line_end]) \
                           and not text[:i].rstrip().endswith('['):
                            rw.record(lit[0], '%s:%d' % (relpath, line_of(text, i)))
                            rw.add_edit(i, end, '_T(%s)' % lua_quote(lit[0]))
                i = end
                continue
            i += 1

    # ---- 5. wide UI literal scan (records only, never edits the source)
    scan_ui_literals(relpath, text, rw, covered)

    # ---- 6. named string arrays whose entries look like identifiers
    for tname in EXTRA_TABLE_SCAN.get(fname, []):
        m = re.search(tname + r'\s*=\s*[\r\n\s]*\{', text)
        if m:
            open_idx = text.index('{', m.start())
            close_idx = match_bracket(text, open_idx)
            if close_idx > 0:
                body = text[open_idx:close_idx]
                for lit in re.finditer(r'"([^"\\\n]{1,60})"', body):
                    v = lit.group(1)
                    if re.search(r'[A-Za-z]', v):
                        rw.record(v, 'ui:%s:%d' % (relpath, line_of(text, open_idx)))

    return rw


# ---------------------------------------------------------------- CSV data
CSV_FIELDS = {
    'ObjectData':    ['name', 'shortName', 'description', 'unknownDescription',
                      'pickupAlertBoxText', 'useVar3'],
    'ActorData':     ['displayName', 'ambientStrings', 'alertStrings',
                      'firstAttackedStrings', 'fleeStrings', 'moveSoundText'],
    'MonsterGroups': ['name'],
    'DialogueData':  ['dialogueSet', 'summary', 'noteForRecap',
                      'tagForNote', 'overwriteTag'],
}
KEYWORD_FIELD = ('DialogueData', 'keyword')


def csv_runtime_value(v):
    """Reproduce what csvLoader.parseSingleField/trim leave in the table."""
    v = v.replace('\u2019', "'").replace('\r', '')
    if v == '' or v == 'NA':
        return None
    if ';' in v or '::' in v:      # becomes a sub-table in the game - not a string
        return None
    try:
        float(v.replace(',', ''))
        if re.fullmatch(r'-?[\d.,]+', v):
            return None
    except ValueError:
        pass
    return v.strip()


def extract_from_csvs(src):
    out = []
    kws = []
    d = os.path.join(src, 'data')
    if not os.path.isdir(d):
        return out, kws
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.csv'):
            continue
        base = re.sub(r'\s*-\s*Sheet1$', '', fn[:-4])
        fields = CSV_FIELDS.get(base)
        if not fields and base != KEYWORD_FIELD[0]:
            continue
        path = os.path.join(d, fn)
        with open(path, newline='', encoding='utf-8', errors='replace') as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                for col in (fields or []):
                    v = row.get(col)
                    if not v:
                        continue
                    if ';' in v:
                        # the game splits this column into an array of lines
                        for part in v.split(';'):
                            rv = csv_runtime_value(part)
                            if rv and translatable(rv):
                                out.append((rv, 'data/%s:%s' % (base, col)))
                        continue
                    rv = csv_runtime_value(v)
                    if rv and translatable(rv):
                        out.append((rv, 'data/%s:%s' % (base, col)))
                if base == KEYWORD_FIELD[0]:
                    v = row.get(KEYWORD_FIELD[1])
                    if v and v != 'NA':
                        rv = csv_runtime_value(v)
                        if rv:
                            kws.append((rv, 'data/DialogueData:keyword'))
    return out, kws


def extract_from_strings_lua(src):
    """Evaluate data/strings.lua with luajit and dump every string value."""
    import subprocess
    p = os.path.join(src, 'data', 'strings.lua')
    if not os.path.isfile(p):
        return []
    luajit = shutil.which('luajit') or '/tmp/LuaJIT/src/luajit'
    if not os.path.isfile(luajit):
        return []
    script = r'''
local t = dofile(arg[1])
local out = {}
local function walk(v)
  if type(v) == "string" then out[#out+1] = v
  elseif type(v) == "table" then for _, x in pairs(v) do walk(x) end end
end
walk(t)
for _, s in ipairs(out) do
  io.write((s:gsub("\\", "\\\\"):gsub("\n", "\\n"):gsub("\t", "\\t")), "\n")
end
'''
    sp = os.path.join('/tmp', '_dump_strings.lua')
    with open(sp, 'w') as f:
        f.write(script)
    try:
        r = subprocess.run([luajit, sp, p], capture_output=True, text=True, timeout=60)
    except Exception:
        return []
    if r.returncode != 0:
        sys.stderr.write('  [warn] strings.lua dump failed: %s\n' % r.stderr.strip()[:200])
        return []
    res = []
    for line in r.stdout.split('\n'):
        if not line:
            continue
        v = line.replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\')
        if translatable(v):
            res.append((v, 'data/strings.lua'))
    return res


# Strings introduced by tools/injections.py (they do not exist in src/)
SYNTHETIC_STRINGS = [
    ('%1 %2 Key', 'gen:dungeon key name'),
    ('%1%2 for unlocking doors in dungeons.', 'gen:dungeon key description'),
    ('%1-%2', 'gen:herb name'),
    ('Day %1 of the %2 Moon', 'gen:calendar date'),
]


# ---------------------------------------------------------------- CSV io
HEADER = ['id', 'context', 'en', 'ko', 'note']


def esc(s):
    return s.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r')


def unesc(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            d = s[i + 1]
            out.append({'n': '\n', 't': '\t', 'r': '\r', '\\': '\\'}.get(d, d))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return ''.join(out)


def read_lang(path):
    rows = OrderedDict()
    cfg = []
    if not os.path.isfile(path):
        return rows, cfg
    with open(path, newline='', encoding='utf-8-sig') as f:
        for r in csv.reader(f):
            if not r or not r[0].strip() or r[0].strip() == 'id':
                continue
            r = (r + [''] * 5)[:5]
            if r[0].startswith('@'):
                cfg.append(r)
                continue
            key = (r[0].strip(), unesc(r[2]))
            rows[key] = r
    return rows, cfg


DEFAULT_CONFIG = [
    ['@font.style', 'pixel | gothic', '', 'pixel', '한글 폰트: pixel=Neo둥근모, gothic=프리텐다드'],
    ['@font.main.size', '', '', '16', '본문 한글 크기(px)'],
    ['@font.mini.size', '', '', '12', '작은 UI 한글 크기(px)'],
    ['@font.big.size', '', '', '32', '큰 글씨 한글 크기(px)'],
    ['@font.title.size', '', '', '120', '타이틀 한글 크기(px)'],
    ['@keyword.style', 'both | en | ko', '', 'both', '대화 키워드 표시: both=한글(English)'],
    ['@build.font.main.size', '', '', '16', '본문 한글 픽셀 크기 (적용.bat 다시 실행해야 반영)'],
    ['@build.font.mono.size', '', '', '16', '고정폭 한글 크기 (적용.bat 다시 실행)'],
    ['@build.font.mini.size', '', '', '11', '작은 UI 한글 크기 (적용.bat 다시 실행)'],
    ['@build.font.big.size',  '', '', '16', '큰 글씨 한글 크기 (적용.bat 다시 실행)'],
]


def write_lang(path, entries, keywords, old_rows, old_cfg):
    """entries/keywords: list of (msgid, context). Existing ko is preserved."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    seen = set()
    out = []
    n_new = n_keep = 0

    def emit(kind, msgid, ctx):
        nonlocal n_new, n_keep
        k = (kind, msgid)
        if k in seen:
            return
        seen.add(k)
        old = old_rows.get(k)
        if old:
            n_keep += 1
            out.append([kind, ctx, esc(msgid), old[3], old[4]])
        else:
            n_new += 1
            out.append([kind, ctx, esc(msgid), '', ''])

    for msgid, ctx in entries:
        emit('S', msgid, ctx)
    for msgid, ctx in keywords:
        emit('K', msgid, ctx)

    # keep translations whose source string vanished (game update) as orphans
    orphans = []
    for (kind, msgid), row in old_rows.items():
        if (kind, msgid) not in seen and row[3]:
            orphans.append([kind, 'ORPHAN(원문 사라짐/변경됨)', esc(msgid), row[3], row[4]])

    cfg = list(old_cfg) if old_cfg else []
    have = {c[0] for c in cfg}
    for d in DEFAULT_CONFIG:
        if d[0] not in have:
            cfg.append(list(d))
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(cfg)
        w.writerow([])
        w.writerows(out)
        if orphans:
            w.writerow([])
            w.writerows(orphans)
    return n_new, n_keep, len(orphans)


# ---------------------------------------------------------------- commands
def iter_lua(src):
    for root, dirs, files in os.walk(src):
        rel_root = os.path.relpath(root, src).replace('\\', '/')
        if rel_root == '.':
            rel_root = ''
        if any((rel_root + '/').startswith(d) for d in SKIP_DIRS):
            continue
        for fn in sorted(files):
            if not fn.endswith('.lua'):
                continue
            rel = (rel_root + '/' + fn).lstrip('/')
            if fn in SKIP_FILES:
                continue
            yield rel, os.path.join(root, fn)


def cmd_unpack(a):
    if os.path.isdir(a.src):
        shutil.rmtree(a.src)
    os.makedirs(a.src)
    with zipfile.ZipFile(a.exe) as z:
        z.extractall(a.src)
    print('unpacked -> %s' % a.src)


def cmd_extract(a):
    entries, keywords = [], []
    stats = {}
    # 주입(injection)으로 새로 생기는 문장도 잡아내려면 주입된 트리를 훑어야 한다
    tmp = tempfile.mkdtemp(prefix='mrloc_x_')
    scan_root = os.path.join(tmp, 'src')
    try:
        shutil.copytree(a.src, scan_root)
        inject(scan_root)
    except Exception as e:
        sys.stderr.write('  주입 미리보기 실패, 원본으로 추출합니다: %s\n' % e)
        shutil.rmtree(tmp, ignore_errors=True)
        scan_root = a.src
        tmp = None
    for rel, path in iter_lua(scan_root):
        text = open(path, encoding='utf-8', errors='replace', newline='').read()
        rw = process_lua(rel, text)
        if rw.msgids:
            stats[rel] = len(rw.msgids)
            entries.extend(rw.msgids)
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    entries.extend(extract_from_strings_lua(a.src))
    entries.extend(SYNTHETIC_STRINGS)
    c, k = extract_from_csvs(a.src)
    entries.extend(c)
    keywords.extend(k)

    old_rows, old_cfg = read_lang(a.lang)
    n_new, n_keep, n_orph = write_lang(a.lang, entries, keywords, old_rows, old_cfg)
    print('extract: %d strings, %d keywords' % (len(entries), len(keywords)))
    print('  new(미번역) %d / kept(번역유지) %d / orphan %d' % (n_new, n_keep, n_orph))
    print('  -> %s' % a.lang)
    if a.verbose:
        for f, n in sorted(stats.items(), key=lambda x: -x[1])[:25]:
            print('   %5d %s' % (n, f))


def cmd_patch(a):
    if os.path.isdir(a.build):
        shutil.rmtree(a.build)
    shutil.copytree(a.src, a.build)

    # structural hooks first (anchors match the pristine source)
    inject(a.build)
    print('injected runtime hooks')

    # then the automatic _T/_F wrapping, over the injected tree
    n_files = n_edits = 0
    for rel, path in iter_lua(a.build):
        text = open(path, encoding='utf-8', errors='replace', newline='').read()
        rw = process_lua(rel, text)
        if not rw.edits:
            continue
        out = rw.apply()
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(out)
        n_files += 1
        n_edits += len(rw.edits)
    print('patched %d lua files, %d call sites' % (n_files, n_edits))

    # runtime + assets
    shutil.copy(os.path.join(ROOT, 'runtime', 'loc.lua'), os.path.join(a.build, 'loc.lua'))
    shutil.copy(os.path.join(ROOT, 'fonts', 'neodgm.ttf'),
                os.path.join(a.build, 'assets', 'kofont_pixel.ttf'))
    shutil.copy(os.path.join(ROOT, 'fonts', 'Pretendard-Regular.ttf'),
                os.path.join(a.build, 'assets', 'kofont_gothic.ttf'))
    os.makedirs(os.path.join(a.build, 'lang'), exist_ok=True)
    if os.path.isfile(a.lang):
        shutil.copy(a.lang, os.path.join(a.build, 'lang', 'ko.csv'))

    # ---- generate the korean BMFonts (original pixel glyphs + hangul) ----
    import fontgen
    rows, cfg = read_lang(a.lang)
    ko_text = ''.join(unesc(r[3]) for r in rows.values() if r[3])
    sizes = {}
    for c in cfg:
        key = c[0]
        if key.startswith('@build.font.') and key.endswith('.size'):
            try:
                sizes[key[len('@build.font.'):-len('.size')]] = int(c[3])
            except (ValueError, IndexError):
                pass
    print('한글 폰트 생성 중...')
    fontgen.generate_all(os.path.join(a.build, 'assets'),
                         os.path.join(a.build, 'assets', 'ko'),
                         ko_text=ko_text, sizes=sizes)


# ------------------------------------------------------------- 게임 폴더 찾기
GAME_PATH_FILE = os.path.join(ROOT, 'game_path.txt')


def _is_game_dir(d):
    if not d:
        return False
    try:
        return (os.path.isfile(os.path.join(d, 'Moonring.exe'))
                or os.path.isfile(os.path.join(d, 'Moonring.exe.bak')))
    except Exception:
        return False


def _steam_libraries():
    libs = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam')):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ('SteamPath', 'InstallPath'):
                        try:
                            v = winreg.QueryValueEx(k, name)[0]
                            if v:
                                libs.append(v.replace('/', os.sep))
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    for d in (r'C:\Program Files (x86)\Steam', r'C:\Program Files\Steam',
              r'D:\Steam', r'D:\SteamLibrary', r'E:\Steam', r'E:\SteamLibrary'):
        libs.append(d)
    extra = []
    for l in libs:
        vdf = os.path.join(l, 'steamapps', 'libraryfolders.vdf')
        try:
            if os.path.isfile(vdf):
                txt = open(vdf, encoding='utf-8', errors='replace').read()
                for m in re.finditer(r'"path"\s*"([^"]+)"', txt):
                    extra.append(m.group(1).replace('\\\\', '\\'))
        except OSError:
            pass
    seen, out = set(), []
    for l in libs + extra:
        if l and l not in seen:
            seen.add(l)
            out.append(l)
    return out


def find_game(hint=None, interactive=True):
    """Moonring.exe 가 있는 폴더를 찾는다.

    순서: --game 인자 -> game_path.txt -> 툴킷의 상위 폴더 -> 스팀 라이브러리
          -> 직접 입력(그리고 game_path.txt 에 기억)
    """
    cands = []
    if hint:
        h = hint
        if os.path.basename(h).lower() == 'moonring.exe':
            h = os.path.dirname(h)
        cands.append(os.path.abspath(h))
    if os.path.isfile(GAME_PATH_FILE):
        try:
            saved = open(GAME_PATH_FILE, encoding='utf-8').read().strip()
            if saved:
                cands.append(saved)
        except OSError:
            pass
    cands.append(os.path.abspath(os.path.join(ROOT, '..')))
    for lib in _steam_libraries():
        cands.append(os.path.join(lib, 'steamapps', 'common', 'Moonring'))

    for c in cands:
        if _is_game_dir(c):
            return os.path.abspath(c)

    if not interactive or not sys.stdin or not sys.stdin.isatty():
        sys.exit('Moonring.exe 가 있는 폴더를 찾지 못했습니다.\n'
                 '  --game "경로" 로 지정하거나, %s 에 경로를 한 줄로 적어 두십시오.'
                 % GAME_PATH_FILE)

    print()
    print('Moonring.exe 가 있는 폴더를 찾지 못했습니다.')
    print('스팀에서  Moonring > 관리 > 로컬 파일 보기  로 폴더를 연 뒤')
    print('주소창의 경로를 붙여넣으십시오. (그냥 Enter 를 치면 취소)')
    while True:
        try:
            typed = input('  Moonring 폴더 경로: ').strip().strip('"')
        except (EOFError, KeyboardInterrupt):
            sys.exit('취소했습니다.')
        if not typed:
            sys.exit('취소했습니다.')
        if os.path.basename(typed).lower() == 'moonring.exe':
            typed = os.path.dirname(typed)
        if _is_game_dir(typed):
            try:
                with open(GAME_PATH_FILE, 'w', encoding='utf-8') as f:
                    f.write(os.path.abspath(typed))
                print('  기억했습니다 -> %s' % GAME_PATH_FILE)
            except OSError:
                pass
            return os.path.abspath(typed)
        print('  그 폴더에 Moonring.exe 가 없습니다. 다시 입력해 주세요.')


def inject(build):
    import injections
    injections.apply_all(build)


def cmd_repack(a):
    with open(a.exe, 'rb') as f:
        data = f.read()
    with zipfile.ZipFile(a.exe) as z:
        stub_len = min(i.header_offset for i in z.infolist())
        stored = {i.filename: i.compress_type for i in z.infolist()}
    stub = data[:stub_len]

    files = []
    for root, dirs, fns in os.walk(a.build):
        for fn in fns:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, a.build).replace('\\', '/')
            files.append((rel, p))
    files.sort()

    tmp = a.out + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(stub)
        with zipfile.ZipFile(f, 'w') as z:
            for rel, p in files:
                ct = stored.get(rel, zipfile.ZIP_STORED)
                z.write(p, rel, compress_type=ct)
    os.replace(tmp, a.out)
    print('repacked -> %s  (%.1f MB, %d entries)' %
          (a.out, os.path.getsize(a.out) / 1e6, len(files)))



# ---------------------------------------------------------------- lint
def cmd_check(a):
    rows, cfg = read_lang(a.lang)
    kws = [msgid for (kind, msgid) in rows if kind == 'K']
    kw_sorted = sorted(kws, key=len, reverse=True)
    problems = []
    n_done = n_todo = 0
    for (kind, en), r in rows.items():
        ko = unesc(r[3])
        ctx = r[1]
        if not ko:
            n_todo += 1
            continue
        n_done += 1
        # 1. reorderable placeholders ('optional' in the note skips this)
        if 'optional' in (r[4] or '').lower():
            pass
        else:
         for i in range(1, 10):
            tok = '%%%d' % i
            if tok in en and tok not in ko:
                problems.append(('PLACEHOLDER', ctx, en, '%s 누락' % tok))
        # 2. printf specifiers (string.format sites)
        bare_en = re.sub(r'%[1-9]', '', en)
        bare_ko = re.sub(r'%[1-9]', '', ko)
        ps_en = re.findall(r'%[-+#0]*[\d.]*[sdifgeExX]', bare_en)
        ps_ko = re.findall(r'%[-+#0]*[\d.]*[sdifgeExX]', bare_ko)
        if ps_en and ps_en != ps_ko:
            problems.append(('FORMAT', ctx, en, '%s -> %s' % (ps_en, ps_ko)))
        # 3. colour tags
        t_en = sorted(re.findall(r'\{[a-zA-Z0-9_]+\}', en))
        t_ko = sorted(re.findall(r'\{[a-zA-Z0-9_]+\}', ko))
        if t_en != t_ko:
            problems.append(('TAG', ctx, en, '%s -> %s' % (t_en, t_ko)))
        # 4. dialogue line separator
        if en.count('||') != ko.count('||'):
            problems.append(('SEPARATOR', ctx, en, '|| 개수 불일치'))
        # 5. typed keywords are checked precisely by tools/kwcheck.py instead
        if False and ctx.startswith('data/DialogueData'):
            for kw in kw_sorted:
                if len(kw) >= 4 and re.search(r'(?<![A-Za-z])' + re.escape(kw) + r'(?![A-Za-z])', en, re.I):
                    if kw.lower() not in ko.lower():
                        problems.append(('KEYWORD', ctx, en, '"%s" 가 번역문에 없음(플레이어가 입력해야 함)' % kw))
                    break
    print('번역 %d / 미번역 %d  (총 %d)' % (n_done, n_todo, n_done + n_todo))
    if not problems:
        print('문제 없음')
        return
    print('문제 %d건:' % len(problems))
    for kind, ctx, en, msg in problems[:a.limit]:
        print('  [%s] %s\n      en: %s\n      %s' % (kind, ctx, en[:90], msg))
    if len(problems) > a.limit:
        print('  ... 외 %d건 (--limit 로 더 보기)' % (len(problems) - a.limit))



# ---------------------------------------------------------------- one-shot
def cmd_build(a):
    """Backup -> unpack from backup -> extract(merge) -> patch -> repack."""
    game = find_game(a.game)
    print('게임 폴더  : %s' % game)
    exe = os.path.join(game, 'Moonring.exe')
    if not os.path.isfile(exe) and os.path.isfile(a.exe):
        exe = a.exe
    if not os.path.isfile(exe):
        sys.exit('Moonring.exe 를 찾을 수 없습니다: %s' % game)
    backup = exe + '.bak'
    if not os.path.isfile(backup):
        print('원본 백업 생성: %s' % backup)
        shutil.copy2(exe, backup)
    else:
        print('기존 백업 사용: %s' % backup)

    # the copy next to the exe is the master once it exists, so edits made
    # in  Moonring\lang\ko.csv  are never lost by a rebuild
    langdir = os.path.join(game, 'lang')
    live = os.path.join(langdir, 'ko.csv')
    if getattr(a, 'push_lang', False) and os.path.isfile(a.lang):
        os.makedirs(langdir, exist_ok=True)
        if os.path.abspath(a.lang) != os.path.abspath(live):
            shutil.copy(a.lang, live)
        print('번역 파일 덮어쓰기(--push-lang): %s' % live)
    if os.path.isfile(live):
        print('번역 파일 사용: %s' % live)
        a.lang = live
    else:
        os.makedirs(langdir, exist_ok=True)
        if os.path.isfile(a.lang):
            shutil.copy(a.lang, live)
        print('번역 파일 설치: %s' % live)
        a.lang = live

    a.exe = backup
    cmd_unpack(a)
    cmd_extract(a)
    cmd_patch(a)

    target = exe if a.replace else os.path.join(game, 'Moonring_KO.exe')
    a.out = target
    cmd_repack(a)

    # keep a backup copy of the translations inside the toolkit folder
    master = os.path.join(ROOT, 'lang', 'ko.csv')
    if os.path.abspath(master) != os.path.abspath(a.lang):
        shutil.copy(a.lang, master)
    rows, _cfg = read_lang(a.lang)
    done = sum(1 for r in rows.values() if r[3])
    print('\n완료. 게임을 실행해 확인하십시오.')
    print('번역 %d / 미번역 %d (미번역은 개발자 콘솔 전용)' % (done, len(rows) - done))
    print('번역 편집: %s' % a.lang)


def cmd_restore(a):
    """한글패치를 지우고 원본 영문판으로 되돌린다."""
    game = find_game(a.game)
    print('게임 폴더  : %s' % game)

    exe = os.path.join(game, 'Moonring.exe')
    bak = exe + '.bak'

    if not os.path.isfile(bak):
        print()
        print('[!] Moonring.exe.bak (원본 백업) 이 없습니다.')
        if os.path.isfile(exe):
            print('    이미 원본이거나, 백업을 지우셨을 수 있습니다.')
        print('    스팀에서  Moonring > 속성 > 설치된 파일 > 게임 파일 무결성 확인')
        print('    을 실행하면 원본 영문판으로 복구됩니다.')
        sys.exit(1)

    try:
        shutil.copy2(bak, exe)
    except PermissionError:
        sys.exit('[!] Moonring.exe 를 바꿀 수 없습니다. 게임이 실행 중인지 확인하세요.')
    os.remove(bak)
    print('원본 복구  : Moonring.exe  (백업 파일은 제거)')

    # 번역 파일은 지우지 않는다 - 여기가 편집용 원본이기 때문
    live = os.path.join(game, 'lang', 'ko.csv')
    if a.purge_lang:
        langdir = os.path.join(game, 'lang')
        master = os.path.join(ROOT, 'lang', 'ko.csv')
        if os.path.isfile(live):
            shutil.copy2(live, master)
            print('번역 백업  : %s' % master)
        shutil.rmtree(langdir, ignore_errors=True)
        print('번역 제거  : %s' % langdir)
    elif os.path.isfile(live):
        print('번역 유지  : %s' % live)
        print('             (편집한 번역이 들어 있어 지우지 않았습니다.')
        print('              완전히 지우려면 --purge-lang 을 붙이십시오)')

    print()
    print('완료. 원본 영문판으로 돌아갔습니다.')
    print('다시 한글로 만들려면 적용.bat 을 실행하십시오.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['unpack', 'extract', 'patch', 'repack', 'check',
                                'build', 'restore'])
    ap.add_argument('--exe', default='Moonring.exe')
    ap.add_argument('--src', default=os.path.join(ROOT, 'src'))
    ap.add_argument('--build', default=os.path.join(ROOT, 'build'))
    ap.add_argument('--lang', default=os.path.join(ROOT, 'lang', 'ko.csv'))
    ap.add_argument('--out', default='Moonring_KO.exe')
    ap.add_argument('-v', '--verbose', action='store_true')
    ap.add_argument('--limit', type=int, default=30)
    ap.add_argument('--game', default=None, help='게임 폴더')
    ap.add_argument('--replace', action='store_true', help='원본 exe 교체')
    ap.add_argument('--push-lang', action='store_true',
                    help='툴킷의 lang/ko.csv 를 게임 폴더로 먼저 밀어넣기')
    ap.add_argument('--purge-lang', action='store_true',
                    help='restore 시 게임 폴더의 lang 도 제거 (툴킷에 백업 후)')
    a = ap.parse_args()
    {'unpack': cmd_unpack, 'extract': cmd_extract, 'patch': cmd_patch,
     'repack': cmd_repack, 'check': cmd_check, 'build': cmd_build,
     'restore': cmd_restore}[a.cmd](a)


if __name__ == '__main__':
    main()
