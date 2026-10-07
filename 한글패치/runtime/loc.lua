--------------------------------------------------------------------
-- Moonring Korean Localisation Runtime  (loc.lua)
--   * Loads lang/ko.csv from the folder next to the exe (editable in Excel)
--   * Falls back to the copy embedded in the .love archive
--   * Provides _T (string), _F (format), _K (dialogue keyword display)
--   * Applies translations to CSV data tables and plain Lua string tables
--   * Hot-reload: alt-tab out, edit ko.csv, alt-tab back in
--------------------------------------------------------------------
local loc = {}

loc.VERSION      = 1
loc.rawText      = false       -- true while drawing pre-translated fragments
loc.strings      = {}          -- msgid -> msgstr
loc.keywords     = {}          -- lowercase english keyword -> korean label
loc.keywordsEn   = {}          -- lowercase english keyword -> canonical english
loc.keywordPlain = {}          -- 화면 표기(소문자) -> 입력해야 하는 영어
loc.tagPlain     = {}          -- 번역된 노트 태그(소문자) -> 영어 원문
loc.config       = {}          -- @key -> value
loc.missing      = {}          -- msgid -> true   (untranslated, for reporting)
loc.loaded       = false
loc.csvPath      = nil

local registry   = {}          -- { {t=table, k=key, orig=originalString}, ... }

--------------------------------------------------------------------
-- helpers
--------------------------------------------------------------------
local function unescape(s)
  if not s or s == "" then return s end
  if not s:find("\\", 1, true) then return s end
  local out, i, n = {}, 1, #s
  while i <= n do
    local c = s:sub(i, i)
    if c == "\\" and i < n then
      local d = s:sub(i + 1, i + 1)
      if     d == "n"  then out[#out+1] = "\n" ; i = i + 2
      elseif d == "t"  then out[#out+1] = "\t" ; i = i + 2
      elseif d == "r"  then out[#out+1] = "\r" ; i = i + 2
      elseif d == "\\" then out[#out+1] = "\\" ; i = i + 2
      elseif d == '"'  then out[#out+1] = '"'  ; i = i + 2
      elseif d == "'"  then out[#out+1] = "'"  ; i = i + 2
      else                  out[#out+1] = c    ; i = i + 1 end
    else
      out[#out+1] = c ; i = i + 1
    end
  end
  return table.concat(out)
end

-- RFC4180-ish CSV parser. Returns array of arrays.
local function parseCSV(text)
  local rows, row, field = {}, {}, {}
  local i, n = 1, #text
  local inQuotes = false
  text = text:gsub("\r\n", "\n"):gsub("\r", "\n")
  n = #text
  while i <= n do
    local c = text:sub(i, i)
    if inQuotes then
      if c == '"' then
        if text:sub(i + 1, i + 1) == '"' then field[#field+1] = '"' ; i = i + 2
        else inQuotes = false ; i = i + 1 end
      else
        field[#field+1] = c ; i = i + 1
      end
    else
      if c == '"' and #field == 0 then
        inQuotes = true ; i = i + 1
      elseif c == "," then
        row[#row+1] = table.concat(field) ; field = {} ; i = i + 1
      elseif c == "\n" then
        row[#row+1] = table.concat(field) ; field = {}
        rows[#rows+1] = row ; row = {} ; i = i + 1
      else
        field[#field+1] = c ; i = i + 1
      end
    end
  end
  if #field > 0 or #row > 0 then
    row[#row+1] = table.concat(field)
    rows[#rows+1] = row
  end
  return rows
end

local function trim(s) return (s:gsub("^%s*(.-)%s*$", "%1")) end

--------------------------------------------------------------------
-- file access
--------------------------------------------------------------------
local function readExternal(path)
  local f = io.open(path, "rb")
  if not f then return nil end
  local d = f:read("*a")
  f:close()
  return d
end

local function findCSV()
  local candidates = {}
  if love and love.filesystem and love.filesystem.getSourceBaseDirectory then
    local base = love.filesystem.getSourceBaseDirectory()
    if base and base ~= "" then
      candidates[#candidates+1] = base .. "/lang/ko.csv"
      candidates[#candidates+1] = base .. "\\lang\\ko.csv"
    end
  end
  candidates[#candidates+1] = "lang/ko.csv"
  for _, p in ipairs(candidates) do
    local d = readExternal(p)
    if d then return d, p end
  end
  -- embedded fallback
  if love and love.filesystem and love.filesystem.getInfo and love.filesystem.getInfo("lang/ko.csv") then
    return love.filesystem.read("lang/ko.csv"), "(embedded)"
  end
  return nil, nil
end

--------------------------------------------------------------------
-- loading
--------------------------------------------------------------------
-- Columns:  id , context , en , ko , note
--   id      : "S" normal string / "K" dialogue keyword / "@..." config
--   context : where it came from (informational only)
--   en      : source english (this IS the lookup key, backslash-escaped)
--   ko      : korean translation (backslash-escaped). Blank = keep english.
function loc.load()
  loc.strings, loc.keywords, loc.config = {}, {}, {}
  loc.keywordsEn = {}
  loc.keywordPlain = {}
  loc.tagPlain = {}
  local data, path = findCSV()
  loc.csvPath = path
  if not data then
    loc.loaded = false
    return false
  end
  -- strip UTF-8 BOM
  if data:sub(1, 3) == "\239\187\191" then data = data:sub(4) end

  local rows = parseCSV(data)
  local count = 0
  for idx = 1, #rows do
    local r = rows[idx]
    local id = trim(r[1] or "")
    if id ~= "" and id ~= "id" then
      if id:sub(1, 1) == "@" then
        loc.config[id] = trim(r[4] or r[3] or "")
      else
        local en = unescape(r[3] or "")
        local ko = unescape(r[4] or "")
        local ctx = r[2] or ""
        if en ~= "" and ko ~= "" then
          if id == "S" and (ctx:find("tagForNote", 1, true)
                            or ctx:find("overwriteTag", 1, true)) then
            -- 노트 태그: 번역문에서 영어 원문을 되찾기 위한 역색인
            loc.tagPlain[ko:lower()] = en
          end
          if id == "K" then
            loc.keywords[en:lower()]   = ko
            loc.keywordsEn[en:lower()] = en
            -- 화면 표기 -> 영어 (자동완성/구름단어가 입력창을 채울 때 되돌리기 위함)
            loc.keywordPlain[(ko .. "(" .. en .. ")"):lower()] = en
            loc.keywordPlain[ko:lower()] = en
          else
            loc.strings[en] = ko
          end
          count = count + 1
        end
      end
    end
  end
  loc.loaded = true
  loc.count = count
  return true
end

function loc.getConfig(key, default)
  local v = loc.config["@" .. key]
  if v == nil or v == "" then return default end
  return v
end

function loc.getConfigNumber(key, default)
  local v = tonumber(loc.getConfig(key, nil))
  if v == nil then return default end
  return v
end

--------------------------------------------------------------------
-- 한글 조사 자동 선택 (josa)
--   번역문에 "이(가)" "을(를)" "은(는)" "와(과)" "(으)로" 같은 표기를 쓰면
--   바로 앞 글자의 받침 유무를 보고 알맞은 조사 하나만 남긴다.
--   앞에 색상 태그({col1} 등)나 키워드 괄호(호박석(Amber))가 있어도 건너뛴다.
--------------------------------------------------------------------
-- marker -> { 받침있음, 받침없음, ㄹ받침을 "없음"으로 볼지 }
local JOSA = {
  ["이(가)"]   = { "이",   "가"   },
  ["가(이)"]   = { "이",   "가"   },
  ["(이)가"]   = { "이",   "가"   },
  ["을(를)"]   = { "을",   "를"   },
  ["를(을)"]   = { "을",   "를"   },
  ["(을)를"]   = { "을",   "를"   },
  ["은(는)"]   = { "은",   "는"   },
  ["는(은)"]   = { "은",   "는"   },
  ["(은)는"]   = { "은",   "는"   },
  ["과(와)"]   = { "과",   "와"   },
  ["와(과)"]   = { "과",   "와"   },
  ["(과)와"]   = { "과",   "와"   },
  ["아(야)"]   = { "아",   "야"   },
  ["야(아)"]   = { "아",   "야"   },
  ["(이)여"]   = { "이여", "여"   },
  ["(이)오"]   = { "이오", "요"   },
  ["(이)라"]   = { "이라", "라"   },
  ["(이)란"]   = { "이란", "란"   },
  ["(이)나"]   = { "이나", "나"   },
  ["(이)든"]   = { "이든", "든"   },
  ["(으)로"]   = { "으로", "로",   true },
  ["으로(로)"] = { "으로", "로",   true },
  ["로(으로)"] = { "으로", "로",   true },
  ["(으)로서"] = { "으로서", "로서", true },
  ["(으)로써"] = { "으로써", "로써", true },
  ["(으)로는"] = { "으로는", "로는", true },
  ["(으)며"]   = { "으며", "며",   true },
  ["(으)면"]   = { "으면", "면",   true },
}
-- 긴 표기를 먼저 검사해야 "(으)로"가 "(으)로서"를 잘라먹지 않는다
local JOSA_KEYS = {}
for k in pairs(JOSA) do JOSA_KEYS[#JOSA_KEYS+1] = k end
table.sort(JOSA_KEYS, function(a, b) return #a > #b end)

-- 숫자 읽기의 받침: 0영 1일 3삼 6육 7칠 8팔 = 있음 / 2이 4사 5오 9구 = 없음
local DIGIT_BATCHIM = { ["0"]=true, ["1"]=true, ["3"]=true, ["6"]=true,
                        ["7"]=true, ["8"]=true,
                        ["2"]=false, ["4"]=false, ["5"]=false, ["9"]=false }
local DIGIT_RIEUL   = { ["1"]=true, ["7"]=true, ["8"]=true }
-- 영문 끝글자를 한국어로 읽었을 때 받침이 없는 글자
local LATIN_NO_BATCHIM = { a=true, e=true, i=true, o=true, u=true,
                           y=true, w=true }
local LATIN_RIEUL      = { l=true, r=true }

-- 문자열 끝에서 UTF-8 한 글자를 떼어낸다
local function lastUtf8(s)
  return s:match("[%z\1-\127\194-\244][\128-\191]*$")
end

local function codepoint(ch)
  if not ch or ch == "" then return nil end
  local b1 = ch:byte(1)
  if b1 < 0x80 then return b1 end
  if b1 >= 0xF0 and #ch >= 4 then
    return (b1-0xF0)*0x40000 + (ch:byte(2)-0x80)*0x1000
         + (ch:byte(3)-0x80)*0x40 + (ch:byte(4)-0x80)
  end
  if b1 >= 0xE0 and #ch >= 3 then
    return (b1-0xE0)*0x1000 + (ch:byte(2)-0x80)*0x40 + (ch:byte(3)-0x80)
  end
  if b1 >= 0xC0 and #ch >= 2 then
    return (b1-0xC0)*0x40 + (ch:byte(2)-0x80)
  end
  return nil
end

-- 조사 앞에 실제로 읽히는 글자를 찾는다 (색상 태그 / 키워드 괄호 건너뜀)
local function readableTail(s)
  for _ = 1, 8 do
    local changed = false
    local n = s:gsub("{[^{}]*}$", "")
    if n ~= s then s, changed = n, true end
    -- "호박석(Amber)" 처럼 한글 뒤에 붙은 원문 괄호는 발음에 쓰지 않는다
    local head = s:match("^(.*)%b()$")
    if head and head ~= "" then
      local cp = codepoint(lastUtf8(head))
      if cp and cp >= 0xAC00 and cp <= 0xD7A3 then
        s, changed = head, true
      end
    end
    if not changed then break end
  end
  return lastUtf8(s)
end

-- returns hasBatchim, isRieul   (nil = 알 수 없음)
local function batchimOf(ch)
  local cp = codepoint(ch)
  if not cp then return nil end
  if cp >= 0xAC00 and cp <= 0xD7A3 then
    local j = (cp - 0xAC00) % 28
    return j ~= 0, j == 8
  end
  if cp >= 0x30 and cp <= 0x39 then
    local d = string.char(cp)
    return DIGIT_BATCHIM[d], DIGIT_RIEUL[d] or false
  end
  if (cp >= 0x41 and cp <= 0x5A) or (cp >= 0x61 and cp <= 0x7A) then
    local c = string.char(cp):lower()
    return not LATIN_NO_BATCHIM[c], LATIN_RIEUL[c] or false
  end
  return nil
end

function loc.josa(s)
  if type(s) ~= "string" or not s:find("(", 1, true) then return s end
  for _, marker in ipairs(JOSA_KEYS) do
    if s:find(marker, 1, true) then
      local rule = JOSA[marker]
      local out, pos = {}, 1
      while true do
        local a, b = s:find(marker, pos, true)
        if not a then out[#out+1] = s:sub(pos) break end
        local head = s:sub(pos, a - 1)
        out[#out+1] = head
        local whole = table.concat(out)
        local has, rieul = batchimOf(readableTail(whole))
        local pick
        if has == nil then
          pick = rule[1]                      -- 알 수 없으면 받침 있는 형태
        elseif rule[3] and rieul then
          pick = rule[2]                      -- ㄹ 받침은 "(으)로" -> "로"
        elseif has then
          pick = rule[1]
        else
          pick = rule[2]
        end
        out[#out+1] = pick
        pos = b + 1
      end
      s = table.concat(out)
    end
  end
  return s
end

--------------------------------------------------------------------
-- translation entry points
--------------------------------------------------------------------
-- Plain string
function loc.T(s)
  if type(s) ~= "string" then return s end
  local t = loc.strings[s]
  if t then return t end
  if s ~= "" then loc.missing[s] = true end
  return s
end

-- Format string with reorderable placeholders:  _F("You hit %1 for %2.", a, b)
-- Korean translation may reorder:               "%1에게 %2의 피해를 입혔다."
function loc.F(fmt, ...)
  local args = { ... }
  local out  = loc.T(fmt)
  for i = 1, #args do
    local v = args[i]
    if v == nil then v = "" else v = tostring(v) end
    -- escape % in the substituted value so gsub does not misinterpret it
    v = v:gsub("%%", "%%%%")
    out = out:gsub("%%" .. i, v)
  end
  return loc.josa(out)
end

-- Display-only format.  Unlike _F this also translates STRING arguments, so a
-- composed label like  " < " .. category .. " > "  shows the korean category.
-- Only used at sites that draw to the screen, never for building ids or paths.
function loc.D(fmt, ...)
  local args = { ... }
  local out  = loc.strings[fmt] or fmt
  for i = 1, #args do
    local v = args[i]
    if v == nil then
      v = ""
    else
      v = tostring(v)
      if not v:find("[\128-\255]") then
        local t = loc.strings[v]
        if t then v = t end
      end
    end
    v = v:gsub("%%", "%%%%")
    out = out:gsub("%%" .. i, v)
  end
  return loc.josa(out)
end

-- 아이템 사용 동사.  data.use 는 "activate" 같은 내부 id 라서 화면에 그대로
-- 나오면 안 된다.  "use:<id>" 로 번역을 찾고, 없으면 메뉴 라벨을 쓴다.
function loc.useVerb(id)
  if type(id) ~= "string" or id == "" then return id end
  local t = loc.strings["use:" .. id]
  if t then return t end
  if G_Globals and G_Globals.useStrings and G_Globals.useStrings[id] then
    return G_Globals.useStrings[id]
  end
  return id
end

-- Dialogue keyword display:  english stays typable, korean shown alongside.
--   _K("Archon")  ->  "아콘(Archon)"     (if a korean label exists)
--                 ->  "Archon"           (if not)
function loc.K(kw)
  if type(kw) ~= "string" or kw == "" then return kw end
  local lower = kw:lower()
  local ko = loc.keywords[lower]
  if not ko then return kw end
  local en = loc.keywordsEn[lower] or kw
  local style = loc.getConfig("keyword.style", "both")
  if style == "en" then return en end
  if style == "ko" then return ko end
  return ko .. "(" .. en .. ")"
end

-- 화면 표기(  꿈(Dreams)  )를 실제로 입력해야 하는 영어(  Dreams  )로 되돌린다.
-- 자동완성/구름 단어가 입력창을 채울 때 쓴다.  모르는 문자열은 그대로 돌려준다.
function loc.plain(s)
  if type(s) ~= "string" or s == "" then return s end
  local en = loc.keywordPlain[s:lower()]
  if en then return en end
  local inner = s:match("^.-%s*%(([^()]+)%)%s*$")
  if inner and inner ~= "" and not inner:find("[\128-\255]") and inner:find("%a") then
    return inner
  end
  return s
end

-- 번역문 안의  꿈(Dream)  표기를 통째로 {col1}...{white} 로 감싼다.
-- Lua 패턴이 아니라 리터럴 검색이라 괄호·한글이 있어도 안전하고,
-- 이미 색이 입혀진 자리는 건너뛰므로 여러 번 불러도 결과가 같다.
function loc.markKeyword(text, en)
  if type(text) ~= "string" or type(en) ~= "string" or en == "" then
    return text, 0
  end
  local ko = loc.keywords[en:lower()]
  if not ko or ko == "" then return text, 0 end
  local want = en:lower()
  local head = ko .. "("
  local out, pos, n = {}, 1, 0
  while true do
    local a = text:find(head, pos, true)
    if not a then break end
    local open  = a + #ko                     -- '(' 의 위치
    local close = text:find(")", open + 1, true)
    local inner = close and text:sub(open + 1, close - 1) or nil
    if inner and inner:lower() == want then
      if text:sub(a - 6, a - 1) == "{col1}" then    -- 이미 색칠됨
        out[#out+1] = text:sub(pos, close)
      else
        out[#out+1] = text:sub(pos, a - 1)
        out[#out+1] = "{col1}" .. text:sub(a, close) .. "{white}"
        n = n + 1
      end
      pos = close + 1
    else
      out[#out+1] = text:sub(pos, open)
      pos = open + 1
    end
  end
  if n == 0 then return text, 0 end
  out[#out+1] = text:sub(pos)
  return table.concat(out), n
end

-- 노트 태그처럼 이미 한국어로 번역된 짧은 이름을  꿈(Dreams)  형태로 되돌린다.
function loc.tagDisplay(s)
  if type(s) ~= "string" or s == "" then return s end
  if s:find("(", 1, true) then return s end            -- 이미 병기되어 있음
  local key = s:lower()
  local en = loc.tagPlain[key] or loc.keywordPlain[key]
  if not en or en:lower() == key then return s end
  local style = loc.getConfig("keyword.style", "both")
  if style == "en" then return en end
  if style == "ko" then return s end
  return s .. "(" .. en .. ")"
end

--------------------------------------------------------------------
-- bulk application to data tables
--------------------------------------------------------------------
local function remember(t, k, orig)
  registry[#registry+1] = { t = t, k = k, orig = orig }
end

-- Deep-translate every string VALUE in a table (keys untouched).
-- Only substitutes when a translation actually exists, so ids pass through.
function loc.applyTable(t, seen, _isReapply)
  if type(t) ~= "table" then return t end
  if seen == nil and not _isReapply then loc.registerReapply(loc.applyTable, t) end
  seen = seen or {}
  if seen[t] then return t end
  seen[t] = true
  for k, v in pairs(t) do
    if type(v) == "string" then
      local tr = loc.strings[v]
      if tr then remember(t, k, v) ; t[k] = tr end
    elseif type(v) == "table" then
      loc.applyTable(v, seen)
    end
  end
  return t
end

-- Which columns of which CSV files hold player-visible text.
-- NOTE: dialogue "keyword" is deliberately NOT here - players type it in english.
loc.csvFields = {
  ["ObjectData"]    = { "name", "shortName", "description", "unknownDescription",
                        "pickupAlertBoxText", "useVar3" },
  -- the *Strings columns are semicolon separated, so the game turns them into
  -- arrays of lines - applyCSV handles both strings and arrays of strings
  ["ActorData"]     = { "displayName", "ambientStrings", "alertStrings",
                        "firstAttackedStrings", "fleeStrings", "moveSoundText" },
  ["MonsterGroups"] = { "name" },
  ["DialogueData"]  = { "dialogueSet", "summary", "noteForRecap",
                        "tagForNote", "overwriteTag" },
}

local function baseName(filename)
  local n = filename:gsub("\\", "/"):match("([^/]+)$") or filename
  n = n:gsub("%.csv$", "")
  n = n:gsub("%s*%-%s*Sheet1$", "")
  return n
end

-- data is  data[rowKey][columnName]
function loc.applyCSV(filename, data, _isReapply)
  if type(data) ~= "table" then return data end
  local fields = loc.csvFields[baseName(filename)]
  if not fields then return data end
  if not _isReapply then loc.registerReapply(loc.applyCSV, filename, data) end
  for _, row in pairs(data) do
    if type(row) == "table" then
      for _, col in ipairs(fields) do
        local v = row[col]
        if type(v) == "string" then
          local tr = loc.strings[v]
          if tr then remember(row, col, v) ; row[col] = tr
          elseif v ~= "" then loc.missing[v] = true end
        elseif type(v) == "table" then
          -- semicolon separated column: an array of lines
          for i, e in pairs(v) do
            if type(e) == "string" then
              local tr = loc.strings[e]
              if tr then remember(v, i, e) ; v[i] = tr
              elseif e ~= "" then loc.missing[e] = true end
            end
          end
        end
      end
    end
  end
  return data
end

--------------------------------------------------------------------
-- hot reload
--------------------------------------------------------------------
loc.reapply = {}
function loc.registerReapply(fn, arg1, arg2)
  loc.reapply[#loc.reapply+1] = { fn = fn, arg1 = arg1, arg2 = arg2 }
end

function loc.reload()
  -- Restore originals first so a re-apply is idempotent.
  -- IMPORTANT: the game transforms some fields after load (dialogueSet is
  -- split into an array of lines).  Writing the original STRING back over a
  -- parsed table breaks the game, so only restore when the type still matches.
  for i = #registry, 1, -1 do
    local e = registry[i]
    if type(e.t[e.k]) == type(e.orig) then
      e.t[e.k] = e.orig
    end
    registry[i] = nil
  end
  loc.load()
  for _, entry in ipairs(loc.reapply) do
    pcall(entry.fn, entry.arg1, entry.arg2, true)
  end
  loc.refreshFonts()
end

--------------------------------------------------------------------
-- report untranslated strings (written to the LOVE save folder)
--------------------------------------------------------------------
function loc.dumpMissing()
  local keys = {}
  for k in pairs(loc.missing) do keys[#keys+1] = k end
  table.sort(keys)
  local out = { "id,context,en,ko,note" }
  for _, k in ipairs(keys) do
    local e = k:gsub("\\", "\\\\"):gsub("\n", "\\n"):gsub("\t", "\\t")
    e = '"' .. e:gsub('"', '""') .. '"'
    out[#out+1] = 'S,runtime-missing,' .. e .. ',,'
  end
  local body = table.concat(out, "\n")
  local written = nil

  -- preferred: right next to the exe, where the translator is already working
  if love and love.filesystem and love.filesystem.getSourceBaseDirectory then
    local base = love.filesystem.getSourceBaseDirectory()
    if base and base ~= "" then
      for _, path in ipairs({ base .. "/lang/ko_missing.csv",
                              base .. "/ko_missing.csv" }) do
        local f = io.open(path, "wb")
        if f then
          f:write("\239\187\191")     -- UTF-8 BOM so excel opens it correctly
          f:write(body)
          f:close()
          written = path
          break
        end
      end
    end
  end

  -- fallback: the LOVE save folder
  if not written and love and love.filesystem then
    pcall(love.filesystem.write, "ko_missing.csv", body)
    written = "(save folder)"
  end

  loc.missingPath = written
  return #keys, written
end

--------------------------------------------------------------------
-- fonts
--------------------------------------------------------------------
-- Korean glyphs are supplied as a FALLBACK so the original pixel font keeps
-- rendering all ascii + the controller glyphs, and the layout stays intact.
loc.fontFiles = {
  pixel  = "assets/kofont_pixel.ttf",
  gothic = "assets/kofont_gothic.ttf",
}

local fontCache = {}
function loc.koFont(size)
  local style = loc.getConfig("font.style", "pixel")
  local path  = loc.fontFiles[style] or loc.fontFiles.pixel
  local key   = style .. ":" .. size
  if fontCache[key] then return fontCache[key] end
  if not (love.filesystem.getInfo and love.filesystem.getInfo(path)) then return nil end
  local ok, f = pcall(love.graphics.newFont, path, size)
  if not ok then return nil end
  if style == "pixel" then f:setFilter("nearest", "nearest") end
  fontCache[key] = f
  return f
end

local fontRegistry = {}

-- attach a korean fallback to an existing font
function loc.attachFallback(font, sizeKey, defaultSize)
  if not font then return end
  fontRegistry[#fontRegistry+1] = { font = font, key = sizeKey, def = defaultSize }
  local size = loc.getConfigNumber(sizeKey, defaultSize)
  local f = loc.koFont(size)
  if not f then return end
  pcall(function() font:setFallbacks(f) end)
end

-- re-attach every registered font (after a style/size change or hot reload)
function loc.refreshFonts()
  for k in pairs(fontCache) do fontCache[k] = nil end
  for _, e in ipairs(fontRegistry) do
    local size = loc.getConfigNumber(e.key, e.def)
    local f = loc.koFont(size)
    if f then pcall(function() e.font:setFallbacks(f) end) end
  end
end

-- Rebuild the game's fonts from the generated BMFonts (original pixel glyphs
-- + korean).  A TrueType fallback cannot be attached to an ImageFont in LOVE,
-- so the fonts themselves are regenerated at build time instead.
function loc.installFonts()
  if not G_Globals then return end
  local st = loc.getFontStyle()
  local function F(n)
    local path = "assets/ko/" .. n .. "_" .. st .. ".fnt"
    if not (love.filesystem.getInfo and love.filesystem.getInfo(path)) then return nil end
    local ok, f = pcall(love.graphics.newFont, path)
    if not ok or not f then
      loc.fontError = tostring(f)
      return nil
    end
    pcall(function() f:setFilter("nearest", "nearest") end)
    return f
  end

  local main, mono = F("main"), F("mainmono")
  local mini, big, dbg = F("mini"), F("big"), F("debug")
  if main then G_Globals.atariFont          = main end
  if mono then G_Globals.atariMonospaceFont = mono end
  if mini then G_Globals.beebTileFont       = mini end
  if big  then G_Globals.beebTileFont2x     = big  end
  if dbg  then G_Globals.debugFont          = dbg  end

  G_Globals.pixelFont         = G_Globals.beebTileFont
  G_Globals.mainFont          = G_Globals.atariFont
  G_Globals.mainMonospaceFont = G_Globals.atariMonospaceFont
  G_Globals.miniFont          = G_Globals.beebTileFont
  G_Globals.textBoxStackFont  = G_Globals.mainFont
  G_Globals.risingTextFont    = G_Globals.mainFont

  -- the title fonts are TrueType, so a real fallback does work for them
  loc.attachFallback(G_Globals.titleFont,    "font.title.size", 120)
  loc.attachFallback(G_Globals.gameOverFont, "font.title.size", 100)

  if G_Globals.mainFont then love.graphics.setFont(G_Globals.mainFont) end
  loc.fontsInstalled = (main ~= nil)
  pcall(loc.hookText)
end

-- switch pixel <-> gothic at runtime
function loc.setFontStyle(style)
  if loc.getFontStyle() == style then return end
  loc.config["@font.style"] = style
  loc.refreshFonts()
  loc.installFonts()
end

function loc.getFontStyle()
  return loc.getConfig("font.style", "pixel")
end


--------------------------------------------------------------------
-- Draw-time translation
--------------------------------------------------------------------
-- Most UI labels are literals handed straight to love.graphics.print /
-- printf (stat names, menu entries, button captions, panel headers).  They
-- are also compared as identifiers elsewhere (`if label == "Show Help"`), so
-- they must NOT be replaced in the data - only on the way to the screen.
local MAX_MISSING = 4000
local missingCount = 0

local function noteMissing(s)
  if missingCount >= MAX_MISSING then return end
  if #s < 2 or #s > 300 then return end
  if not s:find("%a%a") then return end
  if s:find("[\128-\255]") then return end     -- already korean
  if loc.missing[s] == nil then
    loc.missing[s] = true
    missingCount = missingCount + 1
  end
end

function loc.hookDrawing()
  if loc.drawHooked or not (love and love.graphics) then return end
  loc.drawHooked = true

  local _print  = love.graphics.print
  local _printf = love.graphics.printf

  love.graphics.print = function(t, ...)
    if type(t) == "string" then
      local v = loc.strings[t]
      if v then t = v else noteMissing(t) end
      t = loc.josa(t)
    end
    return _print(t, ...)
  end

  love.graphics.printf = function(t, ...)
    if type(t) == "string" then
      local v = loc.strings[t]
      if v then t = v else noteMissing(t) end
      t = loc.josa(t)
    end
    return _printf(t, ...)
  end
end

-- Text handed to a CPrettyText / text box gets the same treatment.
function loc.text(t)
  if type(t) ~= "string" then return t end
  local v = loc.strings[t]
  if v then return loc.josa(v) end
  noteMissing(t)
  return loc.josa(t)
end

-- love.graphics.Text objects (coloured text, title screen, note panel) do not
-- go through print/printf, so patch their shared metatable too.
function loc.hookText()
  if loc.textHooked then return end
  local ok, obj = pcall(love.graphics.newText, love.graphics.getFont(), "")
  if not ok or not obj then return end
  local mt = getmetatable(obj)
  if not mt or type(mt.set) ~= "function" then return end
  loc.textHooked = true

  local function tr(v)
    -- CPrettyText already translated its whole string before splitting it into
    -- coloured fragments.  Translating those fragments again would replace the
    -- english dialogue keywords the player has to type - 꿈(dream) -> 꿈(꿈).
    if loc.rawText then return v end
    if type(v) == "string" then
      local x = loc.strings[v]
      if x then return loc.josa(x) end
      noteMissing(v)
      return loc.josa(v)
    elseif type(v) == "table" then
      local out, changed = {}, false
      for i = 1, #v do
        local e = v[i]
        if type(e) == "string" then
          local x = loc.strings[e]
          if x then out[i] = x ; changed = true
          else out[i] = e ; noteMissing(e) end
        else
          out[i] = e
        end
      end
      if changed then return out end
    end
    return v
  end

  for _, name in ipairs({ "set", "setf", "add", "addf" }) do
    local orig = mt[name]
    if type(orig) == "function" then
      mt[name] = function(self, a, ...) return orig(self, tr(a), ...) end
    end
  end
end

loc.hookDrawing()

--------------------------------------------------------------------
loc.load()

-- convenience globals
_T = loc.T
_F = loc.F
_D = loc.D
_K = loc.K

return loc
