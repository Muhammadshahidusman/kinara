@echo off
REM One-time Earth Engine sign-in (adapted from LPVIS bat_Files\gee_auth.bat).
REM A browser opens: log in with the Google account that owns the project in .env (KINARA_EE_PROJECT), click Allow.
cd /d "%~dp0.."
uv run python -c "import ee; ee.Authenticate()"
uv run python scripts/check_gee.py
pause
