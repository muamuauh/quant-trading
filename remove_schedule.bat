@echo off
chcp 65001 >nul

set "TASK_NAME=qtf_daily"

echo.
echo Removing scheduled task: %TASK_NAME%
echo.

schtasks /Delete /TN %TASK_NAME% /F
if errorlevel 1 (
    echo.
    echo [WARN] Task may not exist, or schtasks /Delete failed.
) else (
    echo.
    echo Task %TASK_NAME% removed.
)

pause
