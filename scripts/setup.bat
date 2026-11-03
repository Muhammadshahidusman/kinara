@echo off
REM One-time setup: installs uv if needed, creates .venv with Python 3.12 and all dependencies.
cd /d "%~dp0.."
where uv >nul 2>nul || (
  echo uv not found. Installing it...
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  echo Close this window, open a new one, and run setup.bat again.
  pause
  exit /b 1
)
uv python install 3.12
uv sync --extra api
uv run pytest
pause
