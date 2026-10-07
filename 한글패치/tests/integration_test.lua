-- 실제 ko.csv 를 읽어 자주 나오는 문장들이 제대로 나오는지 확인
love = nil
local G_Loc = assert(loadfile("runtime/loc.lua"))()

-- csv 를 직접 밀어넣는다 (love.filesystem 없이)
local function loadCSV(path)
  local f = assert(io.open(path, "rb"))
  local text = f:read("*a"); f:close()
  text = text:gsub("^\239\187\191", "")
  local rows, row, cell, q, i = {}, {}, {}, false, 1
  while i <= #text do
    local c = text:sub(i, i)
    if q then
      if c == '"' then
        if text:sub(i+1, i+1) == '"' then cell[#cell+1] = '"'; i = i + 1
        else q = false end
      else cell[#cell+1] = c end
    elseif c == '"' then q = true
    elseif c == "," then row[#row+1] = table.concat(cell); cell = {}
    elseif c == "\n" then
      row[#row+1] = table.concat(cell); cell = {}
      rows[#rows+1] = row; row = {}
    elseif c ~= "\r" then cell[#cell+1] = c end
    i = i + 1
  end
  if #cell > 0 or #row > 0 then row[#row+1] = table.concat(cell); rows[#rows+1] = row end
  return rows
end

local function unescape(s)
  return (s:gsub("\\n", "\n"):gsub("\\t", "\t"))
end

for _, r in ipairs(loadCSV("lang/ko.csv")) do
  if r[1] == "S" and r[3] and r[4] and r[4] ~= "" then
    G_Loc.strings[unescape(r[3])] = unescape(r[4])
  end
end

G_Globals = { useStrings = { activate = "Activate", read = "Read" } }

local checks = {
  { "아이템 사용",
    G_Loc.D(G_Loc.T("You %1 the {col2}%2{white}."), G_Loc.useVerb("activate"), "생명석") },
  { "아이템 사용(받침없음)",
    G_Loc.D(G_Loc.T("You %1 the {col2}%2{white}."), G_Loc.useVerb("read"), "쪽지") },
  { "사용 확인창",
    G_Loc.D("%1 the %2?", G_Loc.useVerb("activate"), "생명석") },
  { "마모",     G_Loc.F("The %1 deteriorates.", "생명석") },
  { "마모(모음)", G_Loc.F("The %1 deteriorates.", "사다리") },
  { "빗나감",   G_Loc.F("{col1}%1 {col2}misses{col1} %2!", "늑대", "당신") },
  { "색상태그", G_Loc.F("Your {col2}%1{white} deteriorates, becoming {col2}%2{white}!", "검", "고철") },
  { "키워드괄호", G_Loc.F("The %1 deteriorates.", "호박석(Amber)") },
}

for _, c in ipairs(checks) do
  print(string.format("%-16s %s", c[1], c[2]))
  assert(not c[2]:find("(", 1, true) or not c[2]:find("이(가)", 1, true), "조사 미해결: " .. c[2])
end
print("통합 테스트 OK")
