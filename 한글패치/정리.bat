@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo [!] Python 3 이 필요합니다.
  echo.
  pause
  exit /b 1
)

echo ============================================
echo  작업 찌꺼기 정리
echo ============================================
python tools\cleanup.py
echo.
pause
