@echo off
title KURINJI Primary Learning Desk Launcher
echo ====================================================
echo Starting KURINJI Speech Translation System...
echo ====================================================

cd /d "%~dp0"

:: 1. Check Python executable
set PYTHON_CMD=python
if exist ".\.venv\Scripts\python.exe" (
    set PYTHON_CMD=.\.venv\Scripts\python.exe
)

:: 2. Check environment file
if not exist ".env" (
    if exist ".env.example" (
        echo Creating .env file from .env.example...
        copy .env.example .env >nul
    )
)

:: 3. Check frontend dependencies
if not exist "frontend\node_modules" (
    echo Installing frontend dependencies (first-time run)...
    cd frontend && call npm install && cd ..
)

:: 4. Start Backend Server
echo Starting Backend API Server (Port 8000)...
start "KURINJI Backend" cmd /k "%PYTHON_CMD% -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload"

:: 5. Start Frontend Dev Server
echo Starting Frontend Client (Port 5173)...
start "KURINJI Frontend" cmd /k "cd frontend && npm run dev"

:: 6. Launch browser
timeout /t 3 /nobreak >nul
echo Opening KURINJI in your browser...
start http://localhost:5173/

echo ====================================================
echo KURINJI is now running!
echo Backend API:  http://127.0.0.1:8000
echo Frontend UI:  http://localhost:5173
echo ====================================================
pause
