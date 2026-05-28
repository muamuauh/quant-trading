@echo off
REM ============================================================
REM  Inner wrapper -- runs run_daily.bat in a child cmd process.
REM  Do not double-click this file directly; use run_daily_safe.bat.
REM
REM  Why a child `cmd /c run_daily.bat` instead of `call`:
REM    - `call` runs the target bat in the SAME cmd process. If the
REM      target's parser crashes, our cmd dies too.
REM    - `cmd /c` spawns a separate child cmd. If THAT one crashes,
REM      we just see a non-zero exit code and keep running.
REM
REM  We're already inside an outer cmd /k window (from run_daily_safe
REM  .bat), so when this script returns, the parent /k holds the
REM  window open until the user types `exit` or closes it.
REM ============================================================

cd /d "%~dp0"

echo.
echo === safe-mode launcher: starting run_daily.bat ===
echo.

cmd /c run_daily.bat %*
set "RC=%errorlevel%"

echo.
echo ============================================================
echo  run_daily.bat finished with exit code: %RC%
echo  Window stays open. Type "exit" or close manually.
echo ============================================================
echo.
