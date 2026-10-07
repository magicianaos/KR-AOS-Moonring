"""Targeted source injections applied to the copied game tree (build/).

These run BEFORE the automatic _T/_F wrapping, so anchors match the pristine
source.  Korean literals injected here contain no ascii letters, so the
extractor ignores them.
"""

import os
import sys

MARK = '--[[KO]]'


class InjectError(Exception):
    pass


_NEWLINE = {}


def _read(path):
    with open(path, encoding='utf-8', errors='replace', newline='') as f:
        raw = f.read()
    _NEWLINE[path] = '\r\n' if '\r\n' in raw else '\n'
    return raw.replace('\r\n', '\n')


def _write(path, s):
    nl = _NEWLINE.get(path, '\n')
    if nl != '\n':
        s = s.replace('\n', nl)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(s)


def sub_once(text, anchor, new, path, required=True):
    if anchor not in text:
        msg = '  [%s] anchor not found: %r' % (os.path.basename(path), anchor[:70])
        if required:
            raise InjectError(msg)
        sys.stderr.write(msg + '\n')
        return text, False
    if text.count(anchor) != 1:
        raise InjectError('  [%s] anchor not unique: %r' % (os.path.basename(path), anchor[:70]))
    return text.replace(anchor, new, 1), True


# --------------------------------------------------------------------- main
MAIN_HEAD = 'G_Loc = require "loc"   ' + MARK + '\n'

FONT_BLOCK = '''
  -- {mark} swap in the generated korean fonts ----------------------------
  G_Loc.installFonts()
  -----------------------------------------------------------------------
'''.replace('{mark}', MARK)

TITLE_FONT_BLOCK = '''
  G_Loc.attachFallback(G_Globals.titleFont,    "font.title.size", 120)   {mark}
  G_Loc.attachFallback(G_Globals.gameOverFont, "font.title.size", 100)   {mark}
'''.replace('{mark}', MARK)

FOCUS_BLOCK = '''

------------------------------------------------------------------ {mark}
-- Hot reload of lang/ko.csv: alt-tab out, save the csv, alt-tab back in.
local _koLastFocus = true
function love.focus(f)
  if G_Loc then pcall(G_Loc.dumpMissing) end
  if f and not _koLastFocus and G_Loc then
    pcall(G_Loc.reload)
  end
  _koLastFocus = f
end

-- On quit, dump every string that appeared in game without a translation
-- to  <save folder>/ko_missing.csv  so it can be pasted into lang/ko.csv.
local _koOldQuit = love.quit
function love.quit()
  if G_Loc then pcall(G_Loc.dumpMissing) end
  if _koOldQuit then return _koOldQuit() end
end
------------------------------------------------------------------------
'''.replace('{mark}', MARK)


def patch_main(build):
    p = os.path.join(build, 'main.lua')
    s = _read(p)
    s = MAIN_HEAD + s

    s, _ = sub_once(
        s,
        'G_Strings              = require "data.strings"',
        'G_Strings              = require "data.strings"\n'
        'G_Loc.applyTable(G_Strings)   ' + MARK,
        p)

    s, _ = sub_once(
        s,
        '  G_Globals.debugFont = love.graphics.newImageFont("assets/beeb.png", G_Globals.supportedCharacters)',
        '  G_Globals.debugFont = love.graphics.newImageFont("assets/beeb.png", G_Globals.supportedCharacters)\n'
        + FONT_BLOCK,
        p)

    s = s + FOCUS_BLOCK
    _write(p, s)


# ---------------------------------------------------------------------- csv
def patch_csv(build):
    p = os.path.join(build, 'library', 'csv.lua')
    s = _read(p)
    s, _ = sub_once(
        s,
        '--  if data == nil then error("Cannot find CSV file with name: " .. filename) end\n  return data',
        '--  if data == nil then error("Cannot find CSV file with name: " .. filename) end\n'
        '  if G_Loc then data = G_Loc.applyCSV(filename, data) end   ' + MARK + '\n'
        '  return data',
        p)
    _write(p, s)


# ------------------------------------------------------------------ globals
def patch_globals(build):
    p = os.path.join(build, 'globals.lua')
    s = _read(p)
    s, _ = sub_once(
        s,
        'G_Options.alwaysShowKeyboard = false',
        'G_Options.alwaysShowKeyboard = false\n'
        'G_Options.koFontPixel = true   ' + MARK,
        p)

    block = '''

------------------------------------------------------------------ {mark}
function G_setKoreanFont(b)
  G_Options.koFontPixel = b
  if G_Loc then G_Loc.setFontStyle(b and "pixel" or "gothic") end
end

function G_getKoreanFont()
  if G_Options.koFontPixel == nil then G_Options.koFontPixel = true end
  return G_Options.koFontPixel
end
------------------------------------------------------------------------

'''.replace('{mark}', MARK)
    for _t in ('stupidCreatureNames', 'traderMadTextArray',
               'traderHateTextArray', 'madnessStrings', 'hengeToDescription'):
        block += ('if G_Loc then G_Loc.applyTable(G_Globals.%s) end   ' % _t
                  + MARK + '\n')
    block += '\n'
    s, _ = sub_once(s, '\nreturn G_Globals', block + 'return G_Globals', p)
    _write(p, s)


# ------------------------------------------------------------- options menu
KO_FONT_ENTRY = '  local ko_font             = {text = "한글 폰트: 픽셀",   leftRightFunction = self.setKoreanFont}   ' + MARK + '\n'

KO_FONT_METHOD = '''

------------------------------------------------------------------ {mark}
function {cls}:setKoreanFont(b)
  if b ~= nil then
    G_setKoreanFont(b)
  end
  return G_getKoreanFont()
end
------------------------------------------------------------------------
'''


def patch_title_screen(build):
    p = os.path.join(build, 'state_title_screen.lua')
    s = _read(p)

    s, _ = sub_once(
        s,
        '  local no_edge_icons       = {text = "No Shortcut Icons",          leftRightFunction = self.setNoEdgeIcons}',
        '  local no_edge_icons       = {text = "No Shortcut Icons",          leftRightFunction = self.setNoEdgeIcons}\n'
        + KO_FONT_ENTRY.rstrip('\n'),
        p)

    if 'no_strobe, "Credits"' in s:
        s = s.replace('no_strobe, "Credits"', 'no_strobe, ko_font, "Credits"')
    else:
        raise InjectError('  [state_title_screen.lua] options list anchor not found')

    s, _ = sub_once(
        s,
        '    if sg.noEdgeIcons == nil then sg.noEdgeIcons = false end',
        '    if sg.noEdgeIcons == nil then sg.noEdgeIcons = false end\n'
        '    if sg.koFontPixel == nil then sg.koFontPixel = true end   ' + MARK,
        p)

    s, _ = sub_once(
        s,
        '  self:setNoEdgeIcons(sg.noEdgeIcons)',
        '  self:setNoEdgeIcons(sg.noEdgeIcons)\n'
        '  self:setKoreanFont(sg.koFontPixel)   ' + MARK,
        p)

    s += KO_FONT_METHOD.replace('{mark}', MARK).replace('{cls}', 'G_stateTitleScreen')
    _write(p, s)


def patch_state_game(build):
    p = os.path.join(build, 'state_game.lua')
    s = _read(p)

    s, _ = sub_once(
        s,
        '  local no_edge_icons         = {text = "No Shortcut Icons",          leftRightFunction = self.setNoEdgeIcons}',
        '  local no_edge_icons         = {text = "No Shortcut Icons",          leftRightFunction = self.setNoEdgeIcons}\n'
        + KO_FONT_ENTRY.rstrip('\n'),
        p)

    n = s.count('no_strobe, jukebox')
    if n == 0:
        raise InjectError('  [state_game.lua] options list anchor not found')
    s = s.replace('no_strobe, jukebox', 'no_strobe, ko_font, jukebox')

    s += KO_FONT_METHOD.replace('{mark}', MARK).replace('{cls}', 'G_stateGame')
    _write(p, s)


# ------------------------------------------------------- dialogue keywords
def patch_speech_area(build):
    """구름/자동완성 표기는  꿈(Dreams)  로 보여주되, 입력창에는 영어만 넣는다.

    표기 그대로 입력창에 들어가면 그 단어가 키워드로 인식되지 않아 대화가 막힌다.
    그래서 태그에 영어 원문(tag.raw)을 따로 들고 다니고, 입력창을 채울 때는
    G_Loc.plain() 으로 항상 영어로 되돌린다.
    """
    p = os.path.join(build, 'speech_area.lua')
    s = _read(p)

    # 1) 떠다니는 키워드 구름: 표시용은 번역, 원문은 tag.raw 에 보관
    s, _ = sub_once(
        s,
        '  local h_wid = 20 + (G_Globals.mainFont:getWidth(text) / 2)',
        '  local ko_raw = text   ' + MARK + '\n'
        '  text = _K(text)   ' + MARK + '\n'
        '  local h_wid = 20 + (G_Globals.mainFont:getWidth(text) / 2)',
        p)
    s, _ = sub_once(
        s,
        '  tag.text = text .. "?"',
        '  tag.text = text .. "?"\n'
        '  tag.raw  = ko_raw   ' + MARK,
        p)

    # 1b) 표시 직전에 '한글(English)' 키워드를 통째로 색칠한다.
    #     초기화 때 한 번만 칠하면 요약(summary) 줄이 빠지고, 핫리로드로
    #     원문을 되돌릴 때 색도 함께 지워진다.  그릴 때마다 칠하면 둘 다 해결.
    s, _ = sub_once(
        s,
        '    text = tools.replaceString(text, id, col .. display_name .. "{white}")\n'
        '  end\n'
        '  return text\n'
        'end',
        '    text = tools.replaceString(text, id, col .. display_name .. "{white}")\n'
        '  end\n'
        '  local ko_kws = self.speakerKeywords[location]\n'
        '                 and self.speakerKeywords[location][self:getSpeakerNameOrGossip()]   ' + MARK + '\n'
        '  if ko_kws and G_Loc and G_Loc.markKeyword then   ' + MARK + '\n'
        '    for _, ko_kw in ipairs(ko_kws) do text = G_Loc.markKeyword(text, ko_kw) end   ' + MARK + '\n'
        '  end   ' + MARK + '\n'
        '  return text\n'
        'end',
        p)

    # 1c) '???' 장소 이름은 표시용이라 번역해도 안전하다.
    #     (내부 식별자 리맵 보호 규칙에 걸려 자동 래핑에서 빠지므로 여기서 명시)
    s, _ = sub_once(
        s,
        'if location == "???" then location = "a secret location" end',
        'if location == "???" then location = _T("a secret location") end   ' + MARK,
        p)

    # 2) 구름 단어를 입력창에 넣을 때 (두 곳)
    n = s.count('self.string = tag.text:sub(1, -2)')
    if n != 2:
        raise InjectError('  [speech_area.lua] 구름 단어 앵커 %d 개 (2개 기대)' % n)
    s = s.replace('self.string = tag.text:sub(1, -2)',
                  'self.string = G_Loc.plain(tag.raw or tag.text:sub(1, -2))   ' + MARK)

    # 3) Tab 자동완성 / Enter 확정도 영어로
    n = s.count('self.string = self.currentTypedTag:lower()')
    if n < 1:
        raise InjectError('  [speech_area.lua] 자동완성 앵커 없음')
    s = s.replace('self.string = self.currentTypedTag:lower()',
                  'self.string = G_Loc.plain(self.currentTypedTag):lower()   ' + MARK)

    _write(p, s)


# ------------------------------------------------- keyword word boundaries
# Dialogue keywords are discovered by a whole-word search over the dialogue
# text.  The stock boundary class only counts  \0 \s , . ? ! ; : -  as word
# separators, so an english keyword written as  아콘(Archon)  would never be
# found once the line is translated.  Widen the class with brackets, quotes
# and every non-ascii byte (i.e. hangul) so korean text still triggers
# keyword discovery.
def patch_tools(build):
    p = os.path.join(build, 'library', 'tools.lua')
    s = _read(p)
    old = ('  if whole_word_only then\n'
           '    pattern = "%f[^%z%s,.?!;:-]".. pattern .."%f[%z%s,.?!;:-]"\n'
           '  end')
    new = ('  if whole_word_only then\n'
           '    local KO_BOUND = "%z%s,.?!;:%-()%[%]<>\'\\"/\\\\|*+&=~`#$@\\128-\\255"   ' + MARK + '\n'
           '    pattern = "%f[^" .. KO_BOUND .. "]" .. pattern .. "%f[" .. KO_BOUND .. "]"\n'
           '  end')
    s, _ = sub_once(s, old, new, p)
    _write(p, s)



# ------------------------------------------------- pretty text draw hook
def patch_pretty_text(build):
    p = os.path.join(build, 'pretty_text.lua')
    s = _read(p)
    s, _ = sub_once(
        s,
        'function CPrettyText:initialize(text, width, style, font)\n  self.shader     = text_shader',
        'function CPrettyText:initialize(text, width, style, font)\n'
        '  if G_Loc then text = G_Loc.text(text) end   ' + MARK + '\n'
        '  self.shader     = text_shader',
        p)
    s, _ = sub_once(
        s,
        'function CPrettyText:setText(text)\n  self.text = text',
        'function CPrettyText:setText(text)\n'
        '  if G_Loc then text = G_Loc.text(text) end   ' + MARK + '\n'
        '  self.text = text',
        p)

    # the fragments are pieces of an already-translated string - do not let the
    # Text hook translate them individually
    n = s.count('self.textObject:setf(fragments, ')
    if n == 0:
        raise InjectError('  [pretty_text.lua] setf anchor not found')
    s = s.replace(
        'self.textObject:setf(fragments, ',
        'if G_Loc then G_Loc.rawText = true end   ' + MARK + '\n  '
        'self.textObject:setf(fragments, ')
    s = s.replace(
        '  self.maxWidth   = self.textObject:getWidth()',
        '  if G_Loc then G_Loc.rawText = false end   ' + MARK + '\n'
        '  self.maxWidth   = self.textObject:getWidth()')
    _write(p, s)



# ------------------------------------------------- procedurally named keys
# Dungeon keys are named  <adjective> <material> Key  and described as
# "A <lowercased name> for unlocking doors in dungeons." - thousands of
# combinations.  Translate the two word lists and the two sentence shapes
# instead of every combination.
def patch_keys(build):
    p = os.path.join(build, 'state_game.lua')
    s = _read(p)
    s, _ = sub_once(
        s,
        '      descriptions[#descriptions + 1] = adjective .. " " .. material .. " Key"',
        '      descriptions[#descriptions + 1] = _F("%1 %2 Key", _T(adjective), _T(material))   ' + MARK,
        p)
    s, _ = sub_once(
        s,
        '      self.objectData[id].description = pre .. new_name .. " for unlocking doors in dungeons."',
        '      self.objectData[id].description = '
        '_F("%1%2 for unlocking doors in dungeons.", pre, new_name)   ' + MARK,
        p)
    _write(p, s)



# --------------------------------------------------- herbs and the calendar
def patch_herbs(build):
    p = os.path.join(build, 'state_game.lua')
    s = _read(p)
    s, _ = sub_once(
        s,
        '      descriptions[#descriptions + 1] = adjective .. "-" .. material',
        '      descriptions[#descriptions + 1] = _F("%1-%2", _T(adjective), _T(material))   ' + MARK,
        p)
    _write(p, s)


def patch_calendar(build):
    p = os.path.join(build, 'calendar.lua')
    s = _read(p)
    s, _ = sub_once(
        s,
        '  local str = "Day " .. (calendar.worldDay + 1)\n'
        '  str = str .. " of the " .. calendar.getMoonAsText() .. " Moon"',
        '  local str = _F("Day %1 of the %2 Moon", calendar.worldDay + 1, '
        'calendar.getMoonAsText())   ' + MARK,
        p)
    _write(p, s)


# ------------------------------------------------- "You activate the X." 문구
def patch_use_text(build):
    """data.use 는 "activate" 같은 내부 id 라 _F 인자로는 번역되지 않는다.
       G_Globals.useStrings 로 표시용 동사를 뽑고 _D 로 문장을 만든다."""
    p = os.path.join(build, 'actions.lua')
    s = _read(p)
    s, _ = sub_once(
        s,
        '    local link = " the "\n'
        '    if not data.isDefiniteArticle then\n'
        '      link = " "\n'
        '    end\n'
        '    actor:addText("You " .. data.use .. link .. "{col2}" '
        '.. CActions.game:getInventoryObjectName(data.ID) .. "{white}.")',
        '    local verb = G_Globals.useStrings[data.use] or data.use   ' + MARK + '\n'
        '    local oname = CActions.game:getInventoryObjectName(data.ID)   ' + MARK + '\n'
        '    if data.isDefiniteArticle then   ' + MARK + '\n'
        '      actor:addText(_D("You %1 the {col2}%2{white}.", verb, oname))   ' + MARK + '\n'
        '    else   ' + MARK + '\n'
        '      actor:addText(_D("You %1 {col2}%2{white}.", verb, oname))   ' + MARK + '\n'
        '    end   ' + MARK,
        p)
    _write(p, s)


# ------------------------------------- 인벤토리 "Activate the X?" 확인 문구
def patch_inventory_use(build):
    p = os.path.join(build, 'inventory_panel.lua')
    s = _read(p)

    # 알림문 안의 소문자 동사 (auto-wrap 이 _F 인자로 넘기므로 여기서 한국어로)
    n = s.count('G_Globals.useStrings[data.use]:lower()')
    if n == 0:
        raise InjectError('  [inventory_panel.lua] useStrings:lower() 앵커 없음')
    s = s.replace('G_Globals.useStrings[data.use]:lower()',
                  'G_Loc.useVerb(data.use)')

    # 확인창 3곳 - 합쳐진 리터럴(" the ?")이 번역 대상이 못 되어 통째로 교체
    s, _ = sub_once(
        s,
        'setActive(G_Globals.useStrings[data.use] .. " the " .. name .. "?", '
        '"Yes", "No", self.game.useItemWithInventoryIndex, self.game, data.ID)',
        'setActive(_D("%1 the %2?", G_Loc.useVerb(data.use), name), '
        '"Yes", "No", self.game.useItemWithInventoryIndex, self.game, data.ID)   ' + MARK,
        p)
    s, _ = sub_once(
        s,
        'setActive(G_Globals.useStrings[data.use] .. " the " .. name .. " with\\n" '
        '.. amount_needed .. "x " .. resource.name.. "?\\n(Cost reduced by {col2}" '
        '.. reduction .. "{white} due to your {col2}Strength{white})"',
        'setActive(_D("%1 the %2 with\\n%3x %4?\\n(Cost reduced by {col2}%5{white} '
        'due to your {col2}Strength{white})", G_Loc.useVerb(data.use), name, '
        'amount_needed, resource.name, reduction)   ' + MARK,
        p)
    s, _ = sub_once(
        s,
        'setActive(G_Globals.useStrings[data.use] .. " the {col2}" .. name .. "{white} with\\n{col2}" '
        '.. amount_needed .. "x " .. resource.name.. "{white}?\\n(Cost reduced by {col2}" '
        '.. reduction .. "{white} due to your {col2}Intellect{white})"',
        'setActive(_D("%1 the {col2}%2{white} with\\n{col2}%3x %4{white}?\\n'
        '(Cost reduced by {col2}%5{white} due to your {col2}Intellect{white})", '
        'G_Loc.useVerb(data.use), name, amount_needed, resource.name, reduction)   ' + MARK,
        p)
    s, _ = sub_once(
        s,
        'setActive(G_Globals.useStrings[data.use] .. " a potion in the " .. name .. " with\\n" '
        '.. amount_needed .. "x " .. resource.name.. "?\\n(Cost reduced by {col2}" '
        '.. reduction.. "{white} with your {col2}Perception{white})"',
        'setActive(_D("%1 a potion in the %2 with\\n%3x %4?\\n(Cost reduced by {col2}%5{white} '
        'with your {col2}Perception{white})", G_Loc.useVerb(data.use), name, '
        'amount_needed, resource.name, reduction)   ' + MARK,
        p)
    _write(p, s)


# --------------------------------------------- "You found 1x <item>!" 습득 문구
def patch_found_text(build):
    """late_messages[#late_messages+1] = "..." .. name .. "..."  는 자동 래핑
       대상이 아니어서 영어로 남는다."""
    for fname, getter in (('actions.lua', 'CActions.game'),
                          ('actor.lua', 'self.actorManager.game')):
        p = os.path.join(build, fname)
        s = _read(p)
        s, _ = sub_once(
            s,
            'late_messages[#late_messages + 1] = "You found {col1}1x " .. '
            '%s:getModifiedObjectName(object_data) .. "{white}!"' % getter,
            'late_messages[#late_messages + 1] = _F("You found {col1}1x %%1{white}!", '
            '%s:getModifiedObjectName(object_data))   %s' % (getter, MARK),
            p)
        _write(p, s)


# ------------------------------------------------- 잠금해제 / 용병 / 돈 문구
def patch_misc_text(build):
    p = os.path.join(build, 'state_game.lua')
    s = _read(p)

    pairs = [
        ('unlock_mechanism = "Orb of " .. unlock_mechanism',
         'unlock_mechanism = _F("Orb of %1", unlock_mechanism)'),
        ('return false, "This door requires a special key and cannot be unlocked with the " '
         '.. unlock_mechanism .. ".", "Cannot unlock!"',
         'return false, _F("This door requires a special key and cannot be unlocked with '
         'the %1.", unlock_mechanism), "Cannot unlock!"'),
        ('return true, "The " .. unlock_mechanism .. " unlocks the door!", "Unlocked!"',
         'return true, _F("The %1 unlocks the door!", unlock_mechanism), "Unlocked!"'),
        ('return true, "The " .. unlock_mechanism .. " unlocks the chest!", "Unlocked!"',
         'return true, _F("The %1 unlocks the chest!", unlock_mechanism), "Unlocked!"'),
        ('return nil, "You cannot use " .. unlock_mechanism .. " to unlock this!", "Unpickable!"',
         'return nil, _F("You cannot use %1 to unlock this!", unlock_mechanism), "Unpickable!"'),
        ('  local currency = "Guineas"\n'
         '  if playerStats.money == 1 then currency = "Guinea" end\n'
         '  return "\\n(You currently have {col1}" .. playerStats.money .. "{white} " .. currency .. ")"',
         '  return _F("\\n(You currently have {col1}%1{white} Guineas)", playerStats.money)'),
        ('G_Strings.spell["spell" .. note_number] = {"The cost is 1x " .. object_data.name, "Spell", spell.name}',
         'G_Strings.spell["spell" .. note_number] = {_F("The cost is 1x %1", object_data.name), '
         '"Spell", spell.name}'),   # note.speaker 로 비교되는 식별자 - 번역 금지
    ]
    for a, b in pairs:
        s, _ = sub_once(s, a, b + '   ' + MARK, p)

    # 용병/추종자 진정시키기 (같은 문장이 두 번 나온다)
    old = ('    local str1 = \'"You hurt me! Pay me {col1}\'\n'
           '    local str2 = " {white}Guineas or you\'re dead!" .. \'"\'\n'
           '    self.multiChoiceBox:setActive("Pay to calm", str1 .. fine .. str2 '
           '.. self:getMoneyAsString(), { "Pay" }, ')
    new_ = ('    local str1 = _F(\'"You hurt me! Pay me {col1}%1 {white}Guineas or you\\\'re '
            'dead!"\', fine)   ' + MARK + '\n'
            '    local str2 = ""   ' + MARK + '\n'
            '    self.multiChoiceBox:setActive("Pay to calm", str1 .. str2 '
            '.. self:getMoneyAsString(), { "Pay" }, ')
    if s.count(old) != 2:
        raise InjectError('  [state_game.lua] 용병 진정 문구 앵커 %d 개' % s.count(old))
    s = s.replace(old, new_)
    _write(p, s)


# ------------------------------------------------ 노트(기록) 태그 병기 표시
def patch_note_panel(build):
    """노트 목록/제목의 태그를  꿈(Dreams)  형태로 보여준다.

    태그는 데이터 단계에서 한국어로 번역되어 있어 노트를 열면 한글만 보이고,
    대화창에서 입력한 영어 단어와 이어지지 않는다.  표시할 때만 병기한다.
    저장 파일의 태그(식별자)는 건드리지 않는다.
    """
    p = os.path.join(build, 'note_panel.lua')
    s = _read(p)

    # 왼쪽 목록
    s, _ = sub_once(
        s,
        '      tools.printTwoThings(left, right, x2 + add_x, y, w-add_x - current_scrollbar_width, col, col)',
        '      if category ~= "Speaker" and category ~= "Location" then   ' + MARK + '\n'
        '        left = G_Loc.tagDisplay(left)   ' + MARK + '\n'
        '      end   ' + MARK + '\n'
        '      tools.printTwoThings(left, right, x2 + add_x, y, w-add_x - current_scrollbar_width, col, col)',
        p)

    # 오른쪽 제목
    n = s.count('love.graphics.printf(v.tag, x, y, w, "center");')
    if n != 2:
        raise InjectError('  [note_panel.lua] 제목 앵커 %d 개 (2개 기대)' % n)
    s = s.replace('love.graphics.printf(v.tag, x, y, w, "center");',
                  'love.graphics.printf(G_Loc.tagDisplay(v.tag), x, y, w, "center");   ' + MARK)

    # 본문의 화자 이름 (Cellera -> 셀레라)
    n = s.count('text = text .. "{col1}" .. v.speaker .. "{white}: " .. t .. "\\n"')
    if n < 1:
        raise InjectError('  [note_panel.lua] 화자 앵커 없음')
    s = s.replace('text = text .. "{col1}" .. v.speaker .. "{white}: " .. t .. "\\n"',
                  'text = text .. "{col1}" .. _T(v.speaker) .. "{white}: " .. t .. "\\n"   ' + MARK)

    # 본문 머리의 태그
    s, _ = sub_once(
        s,
        'text = text .. "{col1}" .. note.tag .. "{white}: " .. t .. "\\n"',
        'text = text .. "{col1}" .. G_Loc.tagDisplay(note.tag) .. "{white}: " .. t .. "\\n"   ' + MARK,
        p)

    # 검색용 문자열
    s, _ = sub_once(
        s,
        '        relevant_strings[#relevant_strings+1] = "{col1}" .. tag .. ":{white} " .. t',
        '        relevant_strings[#relevant_strings+1] = "{col1}" .. G_Loc.tagDisplay(tag) .. ":{white} " .. t   ' + MARK,
        p)

    _write(p, s)


# --------------------------------- 번역된 값을 식별자로 비교하는 자리 바로잡기
def patch_id_compares(build):
    """표시용으로 번역한 문자열을 나중에 `== "영어원문"` 으로 비교하는 곳들.

    번역되면 비교가 영원히 실패해 기능이 조용히 죽는다.  비교 쪽도 _T() 로
    감싸 번역본과 맞춘다 (번역이 없으면 _T 는 원문을 그대로 돌려주므로 안전).
    """
    # 옵션 메뉴: bodyText 가 번역돼 키 처리가 먹지 않았다
    for fname in ('state_title_screen.lua', 'state_game.lua'):
        p = os.path.join(build, fname)
        s = _read(p)
        n = s.count('self.multiChoiceBox.bodyText == "Options"')
        if n == 0:
            raise InjectError('  [%s] Options 비교 앵커 없음' % fname)
        s = s.replace('self.multiChoiceBox.bodyText == "Options"',
                      'self.multiChoiceBox.bodyText == _T("Options")   ' + MARK)
        _write(p, s)

    # 침대에서 잠자기: 선택지 문자열 비교
    p = os.path.join(build, 'state_game.lua')
    s = _read(p)
    s, _ = sub_once(
        s,
        'if choice == "Sleep sneakily (no food)" then',
        'if choice == _T("Sleep sneakily (no food)") then   ' + MARK,
        p)
    s, _ = sub_once(
        s,
        '  elseif choice == "Pay" then',
        '  elseif choice == _T("Pay") then   ' + MARK,
        p)
    # 목록의 "Pay" 는 한 단어라 자동 번역에서 빠졌다 - 명시적으로 감싼다
    n = s.count('{ "Pay", "Sleep sneakily (no food)" }')
    if n:
        s = s.replace('{ "Pay", "Sleep sneakily (no food)" }',
                      '{ _T("Pay"), "Sleep sneakily (no food)" }   ' + MARK)
    _write(p, s)

    # 스킬 트리: 타일 제목 비교
    p = os.path.join(build, 'skill_tree.lua')
    s = _read(p)
    s, _ = sub_once(
        s,
        'elseif self.currentTileTitle == "Devotional Tasks" then',
        'elseif self.currentTileTitle == _T("Devotional Tasks") then   ' + MARK,
        p)
    _write(p, s)


ALL = [patch_main, patch_csv, patch_globals, patch_title_screen,
       patch_state_game, patch_speech_area, patch_tools,
       patch_pretty_text, patch_keys,
       patch_herbs, patch_calendar, patch_use_text,
       patch_inventory_use, patch_found_text, patch_misc_text,
       patch_note_panel, patch_id_compares]


def apply_all(build):
    for fn in ALL:
        fn(build)
