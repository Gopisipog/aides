@echo off
chcp 65001 >nul
title V-LKG Application
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║       V-LKG: Video Leadership Knowledge Graph   ║
echo  ╚══════════════════════════════════════════════════╝
echo.

REM ── Check for arguments ──────────────────────────────────────────────────
set "MODE=web"
if /I "%1"=="--desktop" set "MODE=desktop"
if /I "%1"=="--tray"    set "MODE=tray"
if /I "%1"=="--build"   set "MODE=build"

REM ── Start Docker Desktop if not running ──────────────────────────────────
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [1/4] Starting Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    :wait_docker
    docker info >nul 2>&1
    if %errorlevel% neq 0 (
        timeout /t 2 >nul
        goto wait_docker
    )
) else (
    echo [1/4] Docker Desktop is running.
)

REM ── Start Neo4j if not running ──────────────────────────────────────────
docker ps | findstr neo4j >nul 2>&1
if %errorlevel% neq 0 (
    echo [2/4] Starting Neo4j container...
    docker start neo4j 2>nul || docker run -d --name neo4j -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=neo4j/password neo4j:5-community
) else (
    echo [2/4] Neo4j container is running.
)

REM Wait for Neo4j
echo [3/4] Waiting for Neo4j to be ready...
:wait_neo4j
curl -s http://localhost:7474 >nul 2>&1
if %errorlevel% neq 0 (
    timeout /t 2 >nul
    goto wait_neo4j
)
echo [3/4] Neo4j is ready!

cd /d "%~dp0"

if "%MODE%"=="desktop" (
    echo [4/4] Starting Desktop App...
    echo.
    python desktop_app.py
) else if "%MODE%"=="tray" (
    echo [4/4] Starting Desktop App (tray-only, no window)...
    echo.
    python desktop_app.py --no-window
) else if "%MODE%"=="build" (
    echo [4/4] Building standalone executable...
    echo.
    python build_app.py
) else (
    echo [4/4] Starting Web App (Streamlit)...
    echo.
    python -m streamlit run app.py
)

echo.
pause
