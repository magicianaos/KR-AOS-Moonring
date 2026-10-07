# Moonring 한글화 툴킷

## 내가 할 일 (요약)

1. `적용.bat` 더블클릭 → `Moonring.exe`가 한글판으로 교체됨
   (원본은 `Moonring.exe.bak`로 자동 백업)
2. 게임 실행 → 옵션에서 **"한글 폰트: 픽셀"** 켜고/끄며 폰트 확인
3. 번역을 고치려면 **게임 폴더의** `lang\ko.csv` 를 엑셀로 열어 `ko` 칸만 채우고 저장
   → 게임 재시작(또는 알트탭 후 복귀)
4. 고친 뒤 `번역검사.bat` 한 번 실행
5. 배포본을 만들려면 `배포만들기.bat 1.0.2` (버전을 뒤에 붙임)
6. 되돌리려면 `되돌리기.bat` (게임 폴더의 `lang\ko.csv` 는 남겨 둡니다)
7. 디스크가 부담되면 `정리.bat` — 다시 만들어지는 것만 지웁니다
8. 게임이 업데이트되면 `적용.bat`만 다시 실행 (번역은 그대로 유지됨)

※ Python 3 필요. 없으면 https://www.python.org/downloads/ 에서 설치
   (설치 시 "Add python.exe to PATH" 체크)

---

## 이 폴더는 어디에 둬도 됩니다

게임 폴더 안에 있든 밖에 있든 상관없습니다. 스크립트가 이 순서로 게임을 찾습니다.

1. `--game "경로"` 로 직접 지정한 경로
2. 이 폴더의 `game_path.txt` 에 적힌 경로
3. 이 폴더의 **상위 폴더** (게임 폴더 안에 넣어 둔 경우)
4. 스팀 레지스트리 + `libraryfolders.vdf` 로 찾은 라이브러리들
5. 그래도 못 찾으면 경로를 물어보고, 답한 경로를 `game_path.txt` 에 기억

게임을 다른 드라이브로 옮겼다면 `game_path.txt` 를 지우고 한 번 더 실행하면 됩니다.

---

## 구조

```
아무 곳이나/
└─ 한글패치/                  ← 이 폴더 (툴킷)
   ├─ 적용.bat               게임 exe 를 한글판으로 다시 굽기
   ├─ 되돌리기.bat           원본 영문판으로 복구
   ├─ 번역검사.bat           자리표시자·태그·대화 키워드 검사
   ├─ 배포만들기.bat         배포용 zip 만들기 (인자로 버전)
   ├─ 정리.bat               src/build/옛 배포본 등 재생성 가능한 것 삭제
   ├─ game_path.txt          (자동 생성) 게임 폴더 경로 기억
   ├─ lang/ko.csv            마스터 사본
   ├─ fonts/                 한글 폰트 (OFL)
   ├─ runtime/loc.lua        게임에 주입되는 번역 런타임
   ├─ tools/                 추출·패치·재패킹·배포 스크립트
   ├─ tests/                 LuaJIT 회귀 테스트
   ├─ dist_src/              배포물에 들어갈 적용기·안내문 원본
   ├─ src/   build/          (자동 생성) 원본/패치된 게임 소스 — 지워도 됨
   └─ dist/                  (자동 생성) 배포 zip — 지워도 됨

Moonring/                     ← 게임 폴더 (스팀)
├─ Moonring.exe               한글판 (적용.bat이 만든 것)
├─ Moonring.exe.bak           원본 (자동 백업, 지우지 말 것)
└─ lang/ko.csv                ★ 번역 파일. 엑셀로 여기만 고치면 됨
```

**주의:** `적용.bat` 은 **게임 폴더의** `lang\ko.csv` 를 원본으로 삼습니다.
툴킷 쪽 사본을 밀어넣으려면 `python tools\mrloc.py build --replace --push-lang` 을 쓰십시오.

## ko.csv 편집 규칙

| 열 | 뜻 |
|---|---|
| `id` | `S`=일반 문자열, `K`=대화 키워드, `@...`=설정 |
| `context` | 원문 위치 (참고용, 고치지 말 것) |
| `en` | **원문 = 검색 키. 절대 고치지 말 것** |
| `ko` | ★ 여기에 번역을 씀. 비워두면 영어 그대로 나옴 |
| `note` | 자유 메모 |

- 줄바꿈은 `\n`, 탭은 `\t` 로 씀 (엑셀에서 실제 줄바꿈 넣지 말 것)
- `%1 %2 %3` 은 게임이 값을 끼워넣는 자리 — **순서는 바꿔도 되지만 빠뜨리면 안 됨**
  - 예) `The %1 is no longer %2.` → `%1은(는) 더 이상 %2 상태가 아닙니다.`
- `{col1}` `{white}` 등 중괄호는 색상 태그 — 개수를 원문과 맞출 것
- 대사의 `||` 는 줄 구분 — 개수를 원문과 맞출 것
- **대화 키워드(플레이어가 직접 타이핑하는 단어)는 영어 철자를 번역문 안에 반드시 남길 것**
  - 예) `Ask about the Archon.` → `아콘(Archon)에 대해 묻는다.`
  - `id`가 `K`인 행에 한글 이름을 넣으면 키워드 구름/태그에 `아콘(Archon)` 형태로 표시됨 (입력은 계속 영어)

### 설정 행 (`@`로 시작)

| 키 | 값 | 설명 |
|---|---|---|
| `@font.style` | `pixel` / `gothic` | 기본 한글 폰트 (게임 내 옵션이 우선, 즉시 반영) |
| `@keyword.style` | `both` / `en` / `ko` | 키워드 표시 방식 (`both` = `한글(English)`) |
| `@font.title.size` | 숫자 | 타이틀 한글 크기 (즉시 반영) |
| `@build.font.main.size` | 숫자 | 본문 한글 픽셀 크기 — **바꾼 뒤 `적용.bat` 다시 실행** |
| `@build.font.mini.size` | 숫자 | 작은 UI 한글 크기 — `적용.bat` 다시 실행 |
| `@build.font.mono.size` / `@build.font.big.size` | 숫자 | 고정폭/큰 글씨 — `적용.bat` 다시 실행 |

`@build.font.*` 는 폰트 이미지를 다시 굽기 때문에 재실행이 필요하고,
그 외 설정과 번역문은 게임 재시작(또는 알트탭)만으로 반영됩니다.

## 한글 폰트가 만들어지는 방식

LÖVE는 이미지폰트에 TTF를 폴백으로 붙이는 것을 거부합니다
(`Font fallbacks must be of the same font type`). 그래서 폴백 대신,
**원본 이미지폰트를 글리프 단위로 잘라내 한글 글리프와 함께 BMFont로 다시 굽습니다.**

- 영문·숫자·컨트롤러 아이콘 글리프는 **원본과 픽셀 단위로 동일**
- 한글은 KS X 1001 2,350자 + `ko.csv`에 실제로 쓰인 글자를 추가로 포함
- `pixel`(Neo둥근모) / `gothic`(Pretendard) 두 벌을 모두 구워 두고 게임 내 옵션으로 전환
- 결과물: `assets/ko/*.fnt` + `*.png` (exe 안에 포함, 약 3.7MB)

## 검수 도구

```
python tools\mrloc.py check
```
- 번역/미번역 개수
- `%1` 누락, 색상 태그 불일치, `||` 개수 불일치
- 대사에 있던 **입력용 키워드가 번역문에서 사라진 경우** 경고

## 게임에서 안 잡힌 문자열 찾기

한글판을 플레이하다 영어가 남아 있으면, 게임을 정상 종료했을 때
`%APPDATA%\LOVE\Moonring\ko_missing.csv` 에 그때까지 화면에 나온 미번역 문자열이 쌓입니다.
그 파일 내용을 `lang/ko.csv` 아래에 붙여넣고 번역하면 됩니다.

## 개별 명령 (수동 작업용)

```
python tools\mrloc.py unpack  --exe Moonring.exe.bak   원본 exe → src/
python tools\mrloc.py extract                          src/ → lang/ko.csv (기존 번역 유지)
python tools\mrloc.py patch                            src/ + ko.csv → build/
python tools\mrloc.py repack  --exe Moonring.exe.bak --out Moonring.exe
python tools\mrloc.py build   --game . --replace       위 전부 한 번에
```

## 되돌리기

`Moonring.exe.bak` 를 `Moonring.exe` 로 이름만 바꾸면 원본 복구.
(스팀에서 "게임 파일 무결성 검사"를 해도 원본으로 돌아갑니다)

## 폰트 라이선스

- Neo둥근모 (neodgm) — SIL Open Font License 1.1
- Pretendard — SIL Open Font License 1.1

둘 다 재배포 가능합니다.

## 대화 키워드 검사 (중요)

```
python tools\kwcheck.py
```

게임은 대사 텍스트 안에서 **영어 키워드를 통짜 단어로 문자열 검색**해 플레이어가 배울 키워드를 정합니다.
번역문에서 영어 철자가 사라지면 **그 대화 분기가 영구히 막힙니다.**
이 도구가 게임 로직을 그대로 재현해 누락을 잡아냅니다. 번역을 고친 뒤에는 반드시 한 번 돌려 보십시오.

한글패치는 이를 위해 게임의 단어 경계 판정도 넓혀 뒀습니다(`library/tools.lua`).
원본은 `공백 , . ? ! ; : -` 만 경계로 봐서 `아콘(Archon)` 처럼 괄호로 묶으면 인식하지 못했습니다.
이제 괄호·따옴표·한글까지 경계로 인정하므로 `한글(English)` 형식이 정상 동작합니다.
