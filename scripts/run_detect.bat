@echo off
REM Candidate new-construction alerts from the newest Sentinel-1 passes. Exits quietly when no new pass exists.
REM Appends to data\interim\detect_log.txt. Scheduled daily by schedule_detect.bat.
cd /d "%~dp0.."
echo ===== detect %DATE% %TIME% ===== >> data\interim\detect_log.txt
uv run python -W ignore::DeprecationWarning scripts/detect_alerts.py %* >> data\interim\detect_log.txt 2>&1
