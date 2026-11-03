@echo off
REM Frontend on http://localhost:5173 (needs the API from run_api.bat running).
cd /d "%~dp0..\web"
if not exist node_modules call npm install
npm run dev
