@echo off
REM Starts the baseline Earth Engine exports (flood map on Sentinel-1 orbit 107, 28 Aug 2025)
REM and logs to data\interim\export_log.txt. Check progress later with: run_exports.bat status
cd /d "%~dp0.."
set LOG=data\interim\export_log.txt
if /i "%1"=="status" (
  echo ===== status %DATE% %TIME% ===== >> "%LOG%"
  uv run python -W ignore::DeprecationWarning scripts/export_baseline.py --status >> "%LOG%" 2>&1
  type "%LOG%"
  timeout /t 15
  exit /b
)
echo Kinara exports started %DATE% %TIME% > "%LOG%"
uv run python -W ignore::DeprecationWarning scripts/export_baseline.py --orbit 107 >> "%LOG%" 2>&1
echo ===== status right after start ===== >> "%LOG%"
uv run python -W ignore::DeprecationWarning scripts/export_baseline.py --status >> "%LOG%" 2>&1
echo ===== done %DATE% %TIME% ===== >> "%LOG%"
type "%LOG%"
timeout /t 15
