@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
set "GAME=C:\Games\Among Us"

echo === Among-Us-AI launcher ===
echo.

if not exist "%PY%" (
    echo [ERROR] Python venv not found: %PY%
    echo        Create it with:  py -3.12 -m venv .venv
    echo        Then:            .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "%GAME%\BepInEx\plugins\AmongUsAI.dll" (
    echo [ERROR] BepInEx plugin missing from %GAME%\BepInEx\plugins
    echo.
    pause
    exit /b 1
)

if not exist "%GAME%\BepInEx\interop" (
    echo [ERROR] BepInEx interop assemblies missing - the game has not been
    echo        launched once with BepInEx installed. Start Among Us first.
    echo.
    pause
    exit /b 1
)

rem --- game window / resolution check ---
"%PY%" check_game.py
if errorlevel 1 (
    echo.
    echo [WARN] Task solving and chat will misbehave at the wrong resolution.
    echo.
)

rem --- Ollama connectivity check ---
"%PY%" check_ollama.py
if errorlevel 2 (
    echo.
    echo [WARN] Chat will be disabled or may fail. See above.
    echo.
)

echo [OK] Game dir   : %GAME%
echo [OK] Python     : %PY%
echo.
echo ---------------------------------------------------------------
echo  1. Start Among Us and get INTO a match first.
echo     The bot reads sendData.txt, which the BepInEx plugin only
echo     writes once players exist on the map.
echo  2. Then run this script.
echo  3. Hold the ` key at any time to stop the bot.
echo ---------------------------------------------------------------
echo.

"%PY%" main.py

echo.
echo Bot exited (code %errorlevel%).
pause
