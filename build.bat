@echo off
rem Builds dist\FollowingEyes.exe: one file you can send to friends.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install -q pyinstaller
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --console ^
    --name FollowingEyes ^
    --add-data "model;model" ^
    --hidden-import schermen ^
    --exclude-module matplotlib ^
    ogen.py
echo.
echo Done: dist\FollowingEyes.exe
