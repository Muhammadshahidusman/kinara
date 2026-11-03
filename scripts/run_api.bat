@echo off
REM Starts the Kinara API on http://localhost:8000  (Swagger UI: http://localhost:8000/docs)
cd /d "%~dp0.."
uv run uvicorn kinara.api.main:app --reload --port 8000
