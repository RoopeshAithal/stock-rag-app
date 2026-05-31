@echo off
REM ============================================================
REM  Hybrid Stock-RAG daily pipeline
REM
REM  This .bat is what Windows Task Scheduler runs.
REM  Edit PYTHON_EXE below if you want a specific interpreter
REM  (e.g. a venv: C:\Users\roope\Python\stock_rag_app\.venv\Scripts\python.exe).
REM ============================================================

setlocal

set PROJECT_DIR=c:\Users\roope\Python\stock_rag_app
set PYTHON_EXE=python

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
    echo Failed to cd into %PROJECT_DIR%
    exit /b 1
)

REM Run pipeline. Logs go to logs\daily_YYYYMMDD.log (also handled inside Python).
"%PYTHON_EXE%" -m stock_app.cli daily --horizon 5 --days 365

endlocal
exit /b %ERRORLEVEL%
