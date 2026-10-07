@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo [!] Python 3 이 필요합니다.
  echo     https://www.python.org/downloads/ 에서 설치하세요.
  echo     설치할 때 "Add python.exe to PATH" 를 반드시 체크하십시오.
  echo.
  pause
  exit /b 1
)

echo ============================================
echo  Moonring 한글패치 적용
echo ============================================
echo.
python tools\mrloc.py build --replace
if errorlevel 1 (
  echo.
  echo [!] 실패했습니다. 위 메시지를 확인하세요.
  pause
  exit /b 1
)
echo.
echo 번역 파일은 게임 폴더의 lang\ko.csv 입니다 (엑셀로 편집)
echo.
pause
