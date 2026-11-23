@echo off
rem ============================================================
rem  Following Eyes - installer
rem  Stuur ALLEEN dit bestand. Het haalt de rest van GitHub.
rem  Je vriend dubbelklikt het een keer; daarna start het vanzelf.
rem ============================================================
setlocal
title Following Eyes - installeren...
set "DOEL=%LOCALAPPDATA%\FollowingEyes"
set "ZIP=%TEMP%\following-eyes.zip"
set "URL=https://github.com/LarsLiekens1/following-eyes/archive/refs/heads/main.zip"

echo.
echo   Following Eyes wordt klaargezet. Dit duurt even...
echo.

rem --- 1. Python zoeken, anders installeren via winget ---
set "PY="
for %%P in (py python) do (
    if not defined PY ( %%P -c "import sys" >nul 2>nul && set "PY=%%P" )
)
if not defined PY (
    echo   Python wordt geinstalleerd ^(eenmalig^)...
    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements >nul 2>nul
    if errorlevel 1 (
        echo.
        echo   Kon Python niet automatisch installeren.
        echo   Installeer het zelf via https://www.python.org/downloads/
        echo   en vink "Add python.exe to PATH" aan. Start dit daarna opnieuw.
        pause
        exit /b 1
    )
    set "PY=python"
)

rem --- 2. Code van GitHub downloaden en uitpakken ---
echo   Bestanden downloaden...
curl -L -o "%ZIP%" "%URL%" || ( echo Download mislukt. Internet? & pause & exit /b 1 )
if exist "%DOEL%" rmdir /s /q "%DOEL%"
mkdir "%DOEL%"
tar -xf "%ZIP%" -C "%DOEL%" --strip-components=1 || ( echo Uitpakken mislukt. & pause & exit /b 1 )
del "%ZIP%" >nul 2>nul

rem --- 3. Virtuele omgeving + packages ---
echo   Benodigdheden installeren ^(kan 1-2 minuten duren^)...
cd /d "%DOEL%"
%PY% -m venv .venv
".venv\Scripts\python.exe" -m pip install -q --upgrade pip >nul 2>nul
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || ( echo Installatie mislukt. & pause & exit /b 1 )

rem --- 4. Een snelkoppeling maken en starten ---
copy /y "%DOEL%\start.bat" "%DOEL%\Following Eyes.bat" >nul 2>nul
echo.
echo   Klaar! Het start nu. Stoppen kan altijd met Esc.
echo   Later opnieuw starten: %DOEL%\start.bat
timeout /t 3 >nul
call "%DOEL%\start.bat"
endlocal
