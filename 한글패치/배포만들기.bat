@echo off
chcp 65001 >nul
cd /d "%~dp0"
set VER=%1
if "%VER%"=="" set VER=1.0
echo ============================================
echo  Moonring 한글패치 배포본 만들기 (v%VER%)
echo ============================================
echo.
python tools\makedist.py --version %VER% --rebuild
if errorlevel 1 goto fail
echo.
echo 완료. dist 폴더의 zip 을 배포하세요.
goto end
:fail
echo.
echo [!] 실패했습니다. 위 메시지를 확인하세요.
:end
echo.
pause
