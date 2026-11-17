@echo off
cd /d "%~dp0"
title Catering Manager

rem --- Erster Start: eigene Python-Umgebung anlegen ---
if not exist ".venv\Scripts\python.exe" (
    echo Erster Start: Python-Umgebung wird eingerichtet ...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo Python wurde nicht gefunden. Bitte von python.org installieren
        echo und dabei "Add python.exe to PATH" anhaken.
        pause
        exit /b 1
    )
)

rem --- Pakete installieren/aktualisieren (schnell, wenn schon vorhanden) ---
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo Installation der Pakete fehlgeschlagen. Internetverbindung pruefen.
    pause
    exit /b 1
)

echo.
echo Catering Manager laeuft auf http://127.0.0.1:5000
echo Zum Beenden dieses Fenster schliessen.
echo.
".venv\Scripts\python.exe" app.py
pause