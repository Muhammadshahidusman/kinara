@echo off
REM Registers a daily Windows Task Scheduler job (09:00) that runs run_detect.bat (TRD.md section 8).
REM Remove it with:  schtasks /delete /tn "Kinara detect" /f
schtasks /create /tn "Kinara detect" /tr "\"%~dp0run_detect.bat\"" /sc daily /st 09:00 /f
pause
