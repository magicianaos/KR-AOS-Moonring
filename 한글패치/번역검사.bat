@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo == 번역/포맷 검사 ==
python tools\mrloc.py check
echo.
echo == 대화 키워드 검사 ==
python tools\kwcheck.py
echo.
echo == 식별자 오번역 검사 ==
python tools\audit_ids.py
echo.
pause
