-- loc.josa 단위 테스트 (love 없이 실행)
love = nil
package.path = "./runtime/?.lua;" .. package.path
local chunk = assert(loadfile("runtime/loc.lua"))
local G_Loc = chunk()

local cases = {
  {"생명석이(가) 마모됩니다.",              "생명석이 마모됩니다."},
  {"사과이(가) 떨어졌다.",                  "사과가 떨어졌다."},
  {"{col2}생명석{white}이(가) 마모됩니다.", "{col2}생명석{white}이 마모됩니다."},
  {"{col2}사과{white}이(가) 떨어졌다.",     "{col2}사과{white}가 떨어졌다."},
  {"호박석(Amber)이(가) 빛난다.",           "호박석(Amber)이 빛난다."},
  {"꿈(dream)을(를) 말했다.",               "꿈(dream)을 말했다."},
  {"검을(를) 들었다.",                      "검을 들었다."},
  {"단검을(를) 들었다.",                    "단검을 들었다."},
  {"모자를(을) 썼다.",                      "모자를 썼다."},
  {"칼은(는) 날카롭다.",                    "칼은 날카롭다."},
  {"창은(는) 길다.",                        "창은 길다."},
  {"바다와(과) 하늘",                       "바다와 하늘"},
  {"산와(과) 강",                           "산과 강"},
  {"검(으)로 공격했다.",                    "검으로 공격했다."},
  {"활(으)로 공격했다.",                    "활로 공격했다."},   -- ㄹ 받침
  {"화살(으)로 공격했다.",                  "화살로 공격했다."},
  {"모자(으)로 막았다.",                    "모자로 막았다."},
  {"3이(가) 남았다.",                       "3이 남았다."},
  {"2이(가) 남았다.",                       "2가 남았다."},
  {"Sword이(가) 부러졌다.",                 "Sword이 부러졌다."},
  {"Rosetta이(가) 부서졌다.",               "Rosetta가 부서졌다."},
  {"검을(를) 창와(과) 바꿨다.",             "검을 창과 바꿨다."},
  {"이미 완성된 문장입니다.",               "이미 완성된 문장입니다."},
  {"영웅(이)여 일어나라",                   "영웅이여 일어나라"},
  {"용사(이)여 일어나라",                   "용사여 일어나라"},
}

local fail = 0
for _, c in ipairs(cases) do
  local got = G_Loc.josa(c[1])
  if got ~= c[2] then
    fail = fail + 1
    print(string.format("FAIL  %s\n  기대: %s\n  실제: %s", c[1], c[2], got))
  end
end
print(string.format("josa 테스트: %d/%d 통과", #cases - fail, #cases))
os.exit(fail == 0 and 0 or 1)
