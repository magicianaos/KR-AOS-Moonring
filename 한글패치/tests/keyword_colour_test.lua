-- 실제 ko.csv 로 markKeyword / tagDisplay 검증
love = nil
local G_Loc = assert(loadfile("runtime/loc.lua"))()

local function loadCSV(path)
  local f = assert(io.open(path, "rb")); local t = f:read("*a"); f:close()
  t = t:gsub("^\239\187\191", "")
  local rows, row, cell, q, i = {}, {}, {}, false, 1
  while i <= #t do
    local c = t:sub(i, i)
    if q then
      if c == '"' then
        if t:sub(i+1, i+1) == '"' then cell[#cell+1] = '"'; i = i + 1 else q = false end
      else cell[#cell+1] = c end
    elseif c == '"' then q = true
    elseif c == "," then row[#row+1] = table.concat(cell); cell = {}
    elseif c == "\n" then row[#row+1] = table.concat(cell); cell = {}; rows[#rows+1] = row; row = {}
    elseif c ~= "\r" then cell[#cell+1] = c end
    i = i + 1
  end
  if #cell > 0 or #row > 0 then row[#row+1] = table.concat(cell); rows[#rows+1] = row end
  return rows
end
local function unesc(s) return (s:gsub("\\n", "\n")) end

for _, r in ipairs(loadCSV("lang/ko.csv")) do
  if r[3] and r[4] and r[4] ~= "" then
    local ctx = r[2] or ""
    if r[1] == "S" then
      G_Loc.strings[unesc(r[3])] = unesc(r[4])
      if ctx:find("tagForNote", 1, true) or ctx:find("overwriteTag", 1, true) then
        G_Loc.tagPlain[r[4]:lower()] = r[3]
      end
    elseif r[1] == "K" then
      G_Loc.keywords[r[3]:lower()]   = r[4]
      G_Loc.keywordsEn[r[3]:lower()] = r[3]
      G_Loc.keywordPlain[(r[4] .. "(" .. r[3] .. ")"):lower()] = r[3]
      G_Loc.keywordPlain[r[4]:lower()] = r[3]
    end
  end
end

local fail = 0
local function eq(label, got, want)
  if got ~= want then
    fail = fail + 1
    print(string.format("FAIL %s\n  기대: %s\n  실제: %s", label, want, got))
  end
end

-- 1) 실제 게임 문장 색칠
local line = G_Loc.strings["Still no Dreams, child?"]
local summ = G_Loc.strings["Maybe your Dream will come tonight?"]
eq("대사줄",
   G_Loc.markKeyword(line, "Dreams"),
   "아직도 {col1}꿈(Dreams){white}을 꾸지 못하나, 아이야?")
eq("요약줄",
   G_Loc.markKeyword(summ, "Dream"),
   "어쩌면 오늘 밤 자네의 {col1}꿈(Dream){white}이 올지도?")

-- 2) 단수/복수가 섞여도 잘못 걸리지 않아야 한다
eq("복수 키워드로 단수 문장 검색", G_Loc.markKeyword(summ, "Dreams"), summ)
eq("단수 키워드로 복수 문장 검색", G_Loc.markKeyword(line, "Dream"), line)

-- 3) 두 번 불러도 결과가 같다 (핫리로드 안전)
local once = G_Loc.markKeyword(line, "Dreams")
eq("두 번 적용해도 동일", G_Loc.markKeyword(once, "Dreams"), once)

-- 4) 등록되지 않은 키워드는 그대로
eq("모르는 키워드", G_Loc.markKeyword(line, "Zzzz"), line)

-- 5) 한 줄에 여러 키워드
local multi = "{col2}아콘(Archon){white}과 꿈(Dreams)에 대하여"
eq("여러 키워드", G_Loc.markKeyword(multi, "Dreams"),
   "{col2}아콘(Archon){white}과 {col1}꿈(Dreams){white}에 대하여")

-- 6) 노트 태그 병기
eq("태그(키워드 유래)", G_Loc.tagDisplay("꿈"), "꿈(Dreams)")
eq("태그(tagForNote 유래)", G_Loc.tagDisplay("칼데라"), "칼데라(Caldera)")
eq("태그(모르는 것은 그대로)", G_Loc.tagDisplay("기록 살펴보기"), "기록 살펴보기")
eq("태그(이미 병기됨)", G_Loc.tagDisplay("꿈(Dreams)"), "꿈(Dreams)")
eq("태그(빈 값)", G_Loc.tagDisplay(""), "")

-- 7) 전체 대사에 대해 색칠이 깨지지 않는지 (태그 짝 검사)
local checked, broken = 0, 0
for en, ko in pairs(G_Loc.strings) do
  if ko:find("(", 1, true) then
    for kw_lower, _ in pairs(G_Loc.keywordsEn) do
      local out = G_Loc.markKeyword(ko, G_Loc.keywordsEn[kw_lower])
      if out ~= ko then
        checked = checked + 1
        local o, c = 0, 0
        for _ in out:gmatch("{col1}") do o = o + 1 end
        for _ in out:gmatch("{white}") do c = c + 1 end
        if c < o then broken = broken + 1 end
        -- 원문 글자가 사라지지 않았는지
        if #out < #ko then broken = broken + 1 end
      end
    end
  end
end
print(string.format("실제 번역문 색칠 %d건 검사, 깨짐 %d건", checked, broken))
fail = fail + broken

print(string.format("keyword_colour 테스트: %s", fail == 0 and "통과" or (fail .. "건 실패")))
os.exit(fail == 0 and 0 or 1)
