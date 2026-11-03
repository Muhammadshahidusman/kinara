@echo off
REM Runs the test suite and the Earth Engine check, saving everything to data\interim\check_log.txt
cd /d "%~dp0.."
set LOG=data\interim\check_log.txt
echo Kinara checks started %DATE% %TIME% > "%LOG%"
echo ===== uv sync ===== >> "%LOG%"
uv sync --extra api >> "%LOG%" 2>&1
echo ===== pytest ===== >> "%LOG%"
uv run pytest -rs >> "%LOG%" 2>&1
echo ===== check_gee ===== >> "%LOG%"
uv run python -W ignore::DeprecationWarning scripts/check_gee.py >> "%LOG%" 2>&1
echo ===== done %DATE% %TIME% ===== >> "%LOG%"
type "%LOG%"
timeout /t 15
