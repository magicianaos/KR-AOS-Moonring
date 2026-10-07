-- 실제 ko.csv 의 모든 키워드가  영어 -> 화면표기 -> 영어  로 정확히 돌아오는지
love = nil
local G_Loc = assert(loadfile("runtime/loc.lua"))()

local function loadCSV(path)
  local f = assert(io.open(path, "rb"))
  local text = f:read("*a"); f:close()
  text = text:gsub("^\239\187\191", "")
  local rows, row, cell, q, i = {}, {}, {}, false, 1
  while i <= #text do
    local c = text:sub(i, i)
    if q then
      if c == '"' then
        if text:sub(i+1, i+1) == '"' then cell[#cell+1] = '"'; i = i + 1 else q = false end
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

local n = 0
for _, r in ipairs(loadCSV("lang/ko.csv")) do
  if r[1] == "K" and r[3] and r[4] and r[4] ~= "" then
    local en, ko = r[3], r[4]
    G_Loc.keywords[en:lower()]   = ko
    G_Loc.keywordsEn[en:lower()] = en
    G_Loc.keywordPlain[(ko .. "(" .. en .. ")"):lower()] = en
    G_Loc.keywordPlain[ko:lower()] = en
    n = n + 1
  end
end

local fail, shown = 0, 0
for lower, en in pairs(G_Loc.keywordsEn) do
  for _, style in ipairs({ "both", "ko", "en" }) do
    G_Loc.config["keyword.style"] = style
    local disp = G_Loc.K(en)
    local back = G_Loc.plain(disp)
    -- 게임은 소문자 키로 비교하므로 대소문자는 무시
    if back:lower() ~= lower then
      fail = fail + 1
      if shown < 10 then
        shown = shown + 1
        print(string.format("FAIL [%s] %s -> %s -> %s", style, en, disp, back))
      end
    end
  end
end
G_Loc.config["keyword.style"] = nil

print(string.format("키워드 %d개 x 표기 3종 왕복: 실패 %d건", n, fail))
os.exit(fail == 0 and 0 or 1)
