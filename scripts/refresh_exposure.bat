@echo off
REM Re-fetches Earth Engine inputs (building centroids, river, population, flood scenes) and rebuilds the
REM exposure layers in data\processed. Run after new baseline exports or a threshold change.
cd /d "%~dp0.."
uv run python -W ignore::DeprecationWarning scripts/fetch_inputs.py
uv run python -W ignore::DeprecationWarning scripts/build_exposure.py
pause
