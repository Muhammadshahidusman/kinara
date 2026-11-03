@echo off
cd /d "%~dp0.."
uv run ruff check src tests scripts
uv run pytest
cd web && call npx tsc -b && echo frontend types OK
pause
