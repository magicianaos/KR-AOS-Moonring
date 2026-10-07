#!/usr/bin/env python3
"""Builds BMFont files that contain the game's ORIGINAL pixel glyphs plus Korean.

Why: LÖVE refuses to use a TrueType font as a fallback for an ImageFont
("Font fallbacks must be of the same font type"), so Korean simply does not
render.  Instead we slice the original ImageFont PNGs glyph by glyph, render
the Korean syllables from a TTF, and pack both into one BMFont per font.
The english/controller glyphs stay pixel-identical to the original.
"""

import os
from PIL import Image, ImageDraw, ImageFont

ASCII = (' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`'
         'abcdefghijklmnopqrstuvwxyz{|}~')
GLYPH_ORDER_COUNT = 27          # controller glyphs at 0xE0..0xFA
EXTENDED = ASCII + ''.join(chr(0xE0 + i) for i in range(GLYPH_ORDER_COUNT))

EXTRA_PUNCT = '·…―‘’“”※→←↑↓○●△▲□■◇◆★☆×÷±°㎜㎝㎞㎏㎖㎗㍑℃Ω№'
PAGE_W = 2048


# ---------------------------------------------------------------- imagefont
def slice_imagefont(png_path, chars):
    """Reproduce LÖVE's ImageRasterizer glyph split (runs of non-spacer
    pixels along row 0).  Returns [(char, PIL.Image, advance)]."""
    im = Image.open(png_path).convert('RGBA')
    w, h = im.size
    px = im.load()
    spacer = px[0, 0]
    runs, x = [], 0
    while x < w:
        while x < w and px[x, 0] == spacer:
            x += 1
        s = x
        while x < w and px[x, 0] != spacer:
            x += 1
        if x > s:
            runs.append((s, x))
    runs = runs[:len(chars)]
    if len(runs) < len(chars):
        raise RuntimeError('%s: %d glyphs found, %d expected'
                           % (png_path, len(runs), len(chars)))

    # the trailing glyph often swallows the unused right-hand side of the
    # sheet - clamp it to its ink extent so it does not get a huge advance
    widths = sorted(b - a for a, b in runs)
    median = widths[len(widths) // 2]
    s, e = runs[-1]
    if (e - s) > median * 3:
        sub = im.crop((s, 0, e, h))
        bbox = sub.getbbox()
        e = s + (bbox[2] + 1 if bbox else median)
        runs[-1] = (s, e)

    out = []
    for ch, (s, e) in zip(chars, runs):
        out.append((ch, im.crop((s, 0, e, h)), e - s))
    return out, h


# ------------------------------------------------------------------ korean
def ks_x_1001_syllables():
    """The 2350 hangul syllables of KS X 1001 (what euc-kr can encode)."""
    out = []
    for cp in range(0xAC00, 0xD7A4):
        ch = chr(cp)
        try:
            b = ch.encode('euc_kr')
        except UnicodeEncodeError:
            continue
        if len(b) == 2 and 0xB0 <= b[0] <= 0xC8:
            out.append(ch)
    return out


def korean_charset(extra_text=''):
    chars = set(ks_x_1001_syllables())
    chars.update(EXTRA_PUNCT)
    for ch in extra_text:
        if ord(ch) > 0x7E and ord(ch) < 0xE0 or ord(ch) > 0xFA:
            chars.add(ch)
    chars.discard('\n')
    chars.discard('\t')
    return sorted(chars)


def render_korean(ttf_path, size, chars, pixel=True):
    """Returns {char: (PIL.Image cropped to ink, xoffset, yoffset_from_ascent,
    advance)} plus the font ascent."""
    font = ImageFont.truetype(ttf_path, size)
    ascent, descent = font.getmetrics()
    boxh = ascent + descent
    res = {}
    for ch in chars:
        adv = int(round(font.getlength(ch)))
        if adv <= 0:
            continue
        img = Image.new('L', (adv + size, boxh), 0)
        d = ImageDraw.Draw(img)
        d.text((0, 0), ch, font=font, fill=255)
        if pixel:
            img = img.point(lambda v: 255 if v >= 110 else 0)
        bbox = img.getbbox()
        if bbox is None:
            res[ch] = (None, 0, 0, adv)
            continue
        glyph = img.crop(bbox)
        rgba = Image.new('RGBA', glyph.size, (255, 255, 255, 0))
        rgba.putalpha(glyph)
        res[ch] = (rgba, bbox[0], bbox[1], adv)
    return res, ascent


# ----------------------------------------------------------------- bmfont
def ascii_baseline(ascii_glyphs):
    """bottom row of ink for capitals without descenders = the baseline"""
    NODESC = 'ABCDEFHIKLMNRTUVWXYZ0123456789'
    d = {c: im for c, im, _ in ascii_glyphs}
    bots = []
    for ch in NODESC:
        im = d.get(ch)
        if im is None:
            continue
        bb = im.getbbox()
        if bb:
            bots.append(bb[3])
    return max(bots) if bots else None


def build_bmfont(out_dir, name, ascii_glyphs, img_h, ko, ko_ascent,
                 line_height, base, ko_advance=None, ko_top=None):
    """ascii_glyphs: [(char, PIL.Image, advance)] taken from the original sheet.
    ko: {char: (img|None, xoff, yoff_from_ascent_top, advance)}"""
    entries = []       # (char, image|None, xoffset, yoffset, xadvance)
    for ch, im, adv in ascii_glyphs:
        entries.append((ch, im, 0, 0, adv))
    if ko_top is None:
        ko_top = base - ko_ascent
    for ch, (im, xo, yo, adv) in sorted(ko.items()):
        entries.append((ch, im, xo, ko_top + yo,
                        ko_advance if ko_advance else adv))

    # pack
    pad = 1
    rows, cur, cur_w, row_h = [], [], 0, 0
    for e in entries:
        w = e[1].size[0] if e[1] else 0
        h = e[1].size[1] if e[1] else 0
        if w == 0:
            continue
        if cur_w + w + pad > PAGE_W:
            rows.append((cur, row_h))
            cur, cur_w, row_h = [], 0, 0
        cur.append((e, cur_w))
        cur_w += w + pad
        row_h = max(row_h, h)
    if cur:
        rows.append((cur, row_h))

    total_h = sum(h + pad for _, h in rows) or 1
    page_h = 1
    while page_h < total_h:
        page_h *= 2
    page = Image.new('RGBA', (PAGE_W, page_h), (255, 255, 255, 0))

    placed = {}
    y = 0
    for row, h in rows:
        for e, x in row:
            page.paste(e[1], (x, y))
            placed[e[0]] = (x, y, e[1].size[0], e[1].size[1])
        y += h + pad

    os.makedirs(out_dir, exist_ok=True)
    png_name = '%s_0.png' % name
    page.save(os.path.join(out_dir, png_name), optimize=True)

    lines = []
    lines.append('info face="%s" size=%d bold=0 italic=0 charset="" unicode=1 '
                 'stretchH=100 smooth=0 aa=1 padding=0,0,0,0 spacing=0,0 outline=0'
                 % (name, line_height))
    lines.append('common lineHeight=%d base=%d scaleW=%d scaleH=%d pages=1 packed=0 '
                 'alphaChnl=0 redChnl=0 greenChnl=0 blueChnl=0'
                 % (line_height, base, PAGE_W, page_h))
    lines.append('page id=0 file="%s"' % png_name)
    lines.append('chars count=%d' % len(entries))
    for ch, im, xo, yo, adv in entries:
        if ch in placed:
            x, yy, w, h = placed[ch]
        else:
            x, yy, w, h = 0, 0, 0, 0
        lines.append('char id=%d x=%d y=%d width=%d height=%d xoffset=%d '
                     'yoffset=%d xadvance=%d page=0 chnl=15'
                     % (ord(ch), x, yy, w, h, xo, yo, adv))
    with open(os.path.join(out_dir, name + '.fnt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return len(entries), page.size


# ------------------------------------------------------------------ driver
# name, source png, charset, korean size, korean advance override, baseline shift
FONT_SPECS = [
    ('main',      'moonring_font_non_monospace.png', EXTENDED, 'main',  None, 0),
    ('mainmono',  'moonring_font.png',               ASCII,    'mono',  None, 0),
    ('mini',      'beeb_non_monospace.png',          ASCII,    'mini',  None, 0),
    ('big',       'beebx2.png',                      ASCII,    'big',   None, 0),
    ('debug',     'beeb.png',                        ASCII,    'mini',  None, 0),
]

DEFAULT_SIZES = {'main': 16, 'mono': 16, 'mini': 10, 'big': 16}
STYLE_FILES = {'pixel': 'kofont_pixel.ttf', 'gothic': 'kofont_gothic.ttf'}


def generate_all(assets_dir, out_dir, ko_text='', sizes=None, verbose=True):
    sizes = dict(DEFAULT_SIZES, **(sizes or {}))
    chars = korean_charset(ko_text)
    made = []
    for style, ttf in STYLE_FILES.items():
        ttf_path = os.path.join(assets_dir, ttf)
        if not os.path.isfile(ttf_path):
            continue
        for name, png, charset, sizekey, adv, shift in FONT_SPECS:
            src = os.path.join(assets_dir, png)
            glyphs, img_h = slice_imagefont(src, charset)
            ko_size = sizes.get(sizekey, 16)
            ko, ko_ascent = render_korean(ttf_path, ko_size, chars,
                                          pixel=(style == 'pixel'))
            ko_adv = None
            if name == 'mainmono':
                ko_adv = glyphs[0][2] * 2      # one hangul == two cells
            # sit the hangul on the same baseline as the original ascii glyphs
            bl = ascii_baseline(glyphs)
            ink_bottom = max((im.size[1] + yo) for im, xo, yo, adv in ko.values()
                             if im is not None)
            ko_top = (bl - ink_bottom + shift) if bl is not None else None
            n, size = build_bmfont(out_dir, '%s_%s' % (name, style), glyphs,
                                   img_h, ko, ko_ascent,
                                   line_height=img_h, base=img_h,
                                   ko_advance=ko_adv, ko_top=ko_top)
            made.append(('%s_%s' % (name, style), n, size))
            if verbose:
                print('  %-16s glyphs=%d page=%dx%d' % (made[-1][0], n, size[0], size[1]))
    return made


if __name__ == '__main__':
    import sys
    generate_all(sys.argv[1], sys.argv[2])
