"""Minimal Lua 5.1 lexical helpers: bracket matching, top-level splitting,
string-literal parsing/quoting.  Enough to safely rewrite call arguments."""

import re

_ESC = {
    'a': '\a', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r',
    't': '\t', 'v': '\v', '\\': '\\', '"': '"', "'": "'", '\n': '\n',
}


def _long_bracket_len(s, i):
    """If s[i:] starts a long bracket [==[ return (level, length of opener), else None."""
    if s[i] != '[':
        return None
    j = i + 1
    lvl = 0
    while j < len(s) and s[j] == '=':
        lvl += 1
        j += 1
    if j < len(s) and s[j] == '[':
        return lvl, j - i + 1
    return None


def skip_atom(s, i):
    """Given index i, if a string/comment/long-bracket starts there, return the
    index just past it. Otherwise return i+1."""
    c = s[i]
    if c in '"\'':
        q = c
        j = i + 1
        while j < len(s):
            if s[j] == '\\':
                j += 2
                continue
            if s[j] == q:
                return j + 1
            if s[j] == '\n':          # unterminated - bail out
                return j
            j += 1
        return len(s)
    if c == '-' and s.startswith('--', i):
        lb = _long_bracket_len(s, i + 2)
        if lb:
            lvl, oplen = lb
            close = ']' + '=' * lvl + ']'
            k = s.find(close, i + 2 + oplen)
            return len(s) if k < 0 else k + len(close)
        k = s.find('\n', i)
        return len(s) if k < 0 else k
    lb = _long_bracket_len(s, i)
    if lb:
        lvl, oplen = lb
        close = ']' + '=' * lvl + ']'
        k = s.find(close, i + oplen)
        return len(s) if k < 0 else k + len(close)
    return i + 1


def match_bracket(s, i):
    """s[i] must be one of ( { [ .  Return index of the matching closer, or -1."""
    pairs = {'(': ')', '{': '}', '[': ']'}
    assert s[i] in pairs, s[i]
    want = pairs[s[i]]
    depth = 0
    j = i
    while j < len(s):
        c = s[j]
        if c in '"\'':
            j = skip_atom(s, j)
            continue
        if c == '-' and s.startswith('--', j):
            j = skip_atom(s, j)
            continue
        if c == '[':
            lb = _long_bracket_len(s, j)
            if lb:
                j = skip_atom(s, j)
                continue
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
            if depth == 0:
                return j if c == want else -1
        j += 1
    return -1


def split_top_level(expr, sep):
    """Split expr on `sep` (',' or '..') at bracket depth 0, skipping strings."""
    parts, depth, start, i = [], 0, 0, 0
    n = len(expr)
    seplen = len(sep)
    while i < n:
        c = expr[i]
        if c in '"\'':
            i = skip_atom(expr, i)
            continue
        if c == '-' and expr.startswith('--', i):
            i = skip_atom(expr, i)
            continue
        if c == '[':
            lb = _long_bracket_len(expr, i)
            if lb:
                i = skip_atom(expr, i)
                continue
        if c in '([{':
            depth += 1
            i += 1
            continue
        if c in ')]}':
            depth -= 1
            i += 1
            continue
        if depth == 0 and expr.startswith(sep, i):
            # '..' must not be part of '...' or a number like 1..2 (rare)
            if sep == '..' and (expr.startswith('...', i) or (i > 0 and expr[i - 1] == '.')):
                i += 1
                continue
            parts.append(expr[start:i])
            i += seplen
            start = i
            continue
        i += 1
    parts.append(expr[start:])
    return parts


STRING_RE = re.compile(r'^\s*(["\'])')


def parse_string_literal(part):
    """If `part` is exactly one Lua short-string literal (plus surrounding
    whitespace), return (value, quotechar). Otherwise None."""
    m = STRING_RE.match(part)
    if not m:
        return None
    q = m.group(1)
    i = m.end() - 1
    end = skip_atom(part, i)
    if part[end:].strip() != '':
        return None
    raw = part[i + 1:end - 1]
    out, k = [], 0
    while k < len(raw):
        c = raw[k]
        if c == '\\' and k + 1 < len(raw):
            d = raw[k + 1]
            if d in _ESC:
                out.append(_ESC[d])
                k += 2
                continue
            if d.isdigit():
                num = ''
                k += 1
                while k < len(raw) and raw[k].isdigit() and len(num) < 3:
                    num += raw[k]
                    k += 1
                out.append(chr(int(num)))
                continue
            out.append(d)
            k += 2
            continue
        out.append(c)
        k += 1
    return ''.join(out), q


def lua_quote(s):
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        else:
            out.append(ch)
    out.append('"')
    return ''.join(out)


def iter_code_spans(s):
    """Yield (start, end) spans of s that are actual code (not string/comment)."""
    i, n = 0, len(s)
    start = 0
    while i < n:
        c = s[i]
        if c in '"\'' or (c == '-' and s.startswith('--', i)) or (c == '[' and _long_bracket_len(s, i)):
            j = skip_atom(s, i)
            if j > i:
                yield (start, i)
                i = j
                start = i
                continue
        i += 1
    yield (start, n)
