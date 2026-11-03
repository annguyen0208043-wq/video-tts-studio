@echo off
setlocal
cd /d "%~dp0"
title Video TTS Studio
set "PATH=%~dp0.tools\node;%~dp0.tools\ffmpeg\bin;%PATH%"
set "HF_HOME=%~dp0.tools\huggingface"
set "PYTHON=%~dp0..\VieNeu-TTS\.venv\Scripts\python.exe"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [ERROR] VieNeu-TTS Python environment was not found:
    echo %PYTHON%
    echo Install VieNeu-TTS and backend/requirements.txt before running.
    goto :failed
)
"%PYTHON%" "%~dp0scripts\check-server.py"
if errorlevel 20 goto :failed
if errorlevel 10 exit /b 0
if errorlevel 1 goto :failed

if not exist ".env" (
    echo [ERROR] Missing .env file.
    echo Copy .env.example to .env and configure DATABASE_URL first.
    goto :failed
)

if exist "frontend\dist\index.html" goto :backend
where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js and npm are required to build the frontend.
    goto :failed
)
if not exist "frontend\node_modules" (
    call npm.cmd --prefix frontend install
    if errorlevel 1 goto :failed
)
call npm.cmd --prefix frontend run build
if errorlevel 1 goto :failed

:backend
cd /d "%~dp0backend"
"%PYTHON%" -m alembic upgrade head
if errorlevel 1 goto :failed
echo.
echo Open http://127.0.0.1:8765 in your browser after the server starts.
echo Press Ctrl+C to stop the server.
echo.
"%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Startup failed. See the error above.
pause
exit /b 1
