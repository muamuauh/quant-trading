@echo off
chcp 65001 >nul

REM ============================================================
REM  Register a Windows daily scheduled task that runs
REM  run_daily.bat unattended.
REM
REM  Usage:
REM    setup_schedule.bat            -- default 21:00 (pre-US-open CST)
REM    setup_schedule.bat 22:25      -- custom time HH:MM
REM    setup_schedule.bat 21:00 1    -- after creating, run once now to test
REM
REM  The task:
REM    * runs as the current user (so OpenD must be logged in)
REM    * requires user to be logged in (not SYSTEM)
REM    * passes --no-pause --skip-open so the bat exits cleanly
REM    * exit code goes back to Task Scheduler history
REM
REM  To remove: run remove_schedule.bat
REM ============================================================

set "TIME_HHMM=%~1"
if "%TIME_HHMM%"=="" set "TIME_HHMM=21:00"

set "RUN_NOW=%~2"

set "TASK_NAME=qtf_daily"
set "BAT_PATH=%~dp0run_daily.bat"
if "%BAT_PATH:~-1%"=="\" set "BAT_PATH=%BAT_PATH:~0,-1%"

echo.
echo ============================================================
echo  Registering scheduled task
echo    Name:        %TASK_NAME%
echo    Time:        %TIME_HHMM% daily
echo    Command:     "%BAT_PATH%" --no-pause --skip-open
echo ============================================================
echo.

REM Delete any prior task with this name (ignore errors).
schtasks /Delete /TN %TASK_NAME% /F >nul 2>&1

schtasks /Create ^
  /SC DAILY ^
  /TN %TASK_NAME% ^
  /TR "\"%BAT_PATH%\" --no-pause --skip-open" ^
  /ST %TIME_HHMM% ^
  /F

if errorlevel 1 (
    echo.
    echo [FATAL] schtasks /Create failed. Possible reasons:
    echo   - Time format must be HH:MM (24-hour), e.g. 21:25
    echo   - On some Windows builds you may need elevated cmd.
    pause
    exit /b 1
)

echo.
echo --- Task registered. Details: ---
schtasks /Query /TN %TASK_NAME% /FO LIST /V | findstr /R /C:"TaskName" /C:"Status" /C:"Next Run Time" /C:"Last Run Time" /C:"Last Result" /C:"Schedule" /C:"Task To Run" /C:"Run As"

if "%RUN_NOW%"=="1" (
    echo.
    echo --- Running task once now to verify ---
    schtasks /Run /TN %TASK_NAME%
    if errorlevel 1 (
        echo [WARN] /Run failed -- check Task Scheduler GUI for details.
    ) else (
        echo Triggered. Watch a separate cmd window pop up; check logs\qtf.jsonl when it finishes.
    )
)

echo.
echo ============================================================
echo  Done. Task %TASK_NAME% will run daily at %TIME_HHMM%.
echo  To remove:  remove_schedule.bat
echo  To inspect: taskschd.msc  (Task Scheduler GUI)
echo ============================================================
pause
