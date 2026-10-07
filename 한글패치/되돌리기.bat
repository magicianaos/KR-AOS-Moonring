@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo [!] Python 3 이 필요합니다.
  echo     https://www.python.org/downloads/ 에서 설치하세요.
  echo.
  pause
  exit /b 1
)

echo ============================================
echo  Moonring 한글패치 되돌리기
echo ============================================
echo.
echo 원본 영문판으로 되돌립니다.
echo 게임 폴더의 lang\ko.csv (번역 원본) 는 지우지 않습니다.
echo.
set /p YN=진행할까요? (Y/N) : 
if /i not "%YN%"=="Y" (
  echo 취소했습니다.
  echo.
  pause
  exit /b 0
)
echo.
python tools\mrloc.py restore
if errorlevel 1 (
  echo.
  echo [!] 실패했습니다. 위 메시지를 확인하세요.
)
echo.
pause
