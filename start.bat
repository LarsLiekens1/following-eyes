@echo off
rem Dubbelklik dit bestand om de ogen op volledig scherm te starten.
rem Andere kleur? Typ in cmd:  start.bat geel   (of: rood, wit)

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Geen .venv gevonden. Doe eerst:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

rem Windows Terminal aanwezig? Dan openen we een nieuw venster op volledig scherm.
where wt >nul 2>nul
if %errorlevel%==0 (
    start "" wt --fullscreen -d "%~dp0." "%~dp0.venv\Scripts\python.exe" "%~dp0ogen.py" %*
    exit /b 0
)

rem Anders gewoon in dit venster. Druk Alt+Enter voor volledig scherm.
echo Tip: druk Alt+Enter voor volledig scherm.
timeout /t 2 >nul
".venv\Scripts\python.exe" ogen.py %*
