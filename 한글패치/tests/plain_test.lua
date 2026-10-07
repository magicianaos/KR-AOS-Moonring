-- G_Loc.plain 단위 테스트: 화면 표기 -> 입력용 영어
love = nil
local G_Loc = assert(loadfile("runtime/loc.lua"))()

local function reg(en, ko)
  G_Loc.keywords[en:lower()]   = ko
  G_Loc.keywordsEn[en:lower()] = en
  G_Loc.keywordPlain[(ko .. "(" .. en .. ")"):lower()] = en
  G_Loc.keywordPlain[ko:lower()] = en
end
reg("Dreams", "꿈")
reg("Archon", "아콘")
reg("The Serpent's Eye", "뱀의 눈")
reg("Amber", "호박석")

local cases = {
  { "꿈(Dreams)",            "Dreams" },
  { "꿈(dreams)",            "Dreams" },        -- 소문자 표기도
  { "아콘(Archon)",          "Archon" },
  { "뱀의 눈(The Serpent's Eye)", "The Serpent's Eye" },
  { "호박석(Amber)",         "Amber" },
  { "꿈",                    "Dreams" },        -- ko 전용 표기 모드
  { "dreams",                "dreams" },        -- 이미 영어면 그대로
  { "Amber",                 "Amber" },
  { "알수없음(Unknown)",      "Unknown" },       -- 등록 안 됐어도 괄호 안을 씀
  { "",                      "" },
  { "괄호없는한글",           "괄호없는한글" },
}

local fail = 0
for _, c in ipairs(cases) do
  local got = G_Loc.plain(c[1])
  if got ~= c[2] then
    fail = fail + 1
    print(string.format("FAIL  %-28s 기대: %-22s 실제: %s", c[1], c[2], got))
  end
end

-- _K 로 만든 표기가 plain 으로 정확히 되돌아오는지 왕복 검사
for en, _ in pairs(G_Loc.keywordsEn) do
  local disp = G_Loc.K(G_Loc.keywordsEn[en])
  local back = G_Loc.plain(disp)
  if back:lower() ~= en then
    fail = fail + 1
    print(string.format("FAIL 왕복  %s -> %s -> %s", en, disp, back))
  end
end

print(string.format("plain 테스트: %d/%d 통과", #cases - fail, #cases))
os.exit(fail == 0 and 0 or 1)
