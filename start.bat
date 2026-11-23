@echo off
rem Double-click this file to start the eyes in fullscreen.
rem Other color? In cmd type:  start.bat yellow   (or: red, white)

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo No .venv found. First run:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

rem Windows Terminal installed? Then open a new fullscreen window.
where wt >nul 2>nul
if %errorlevel%==0 (
    start "" wt --fullscreen -d "%~dp0." "%~dp0.venv\Scripts\python.exe" "%~dp0ogen.py" %*
    exit /b 0
)

rem Otherwise just run in this window. Press Alt+Enter for fullscreen.
echo Tip: press Alt+Enter for fullscreen.
timeout /t 2 >nul
".venv\Scripts\python.exe" ogen.py %*
