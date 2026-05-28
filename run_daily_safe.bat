@echo off
REM ============================================================
REM  Crash-resistant launcher for run_daily.bat.
REM
REM  Double-click THIS file (not run_daily.bat). It spawns a new
REM  cmd window in /k mode that calls _run_daily_inner.bat, which
REM  in turn runs run_daily.bat as a SEPARATE child cmd process.
REM
REM  Even if run_daily.bat's cmd parser crashes mid-run, only the
REM  inner child cmd dies -- the outer /k window stays open so you
REM  can read whatever was printed before the crash.
REM
REM  Args are passed straight through to run_daily.bat.
REM    --dry-run / --retrain / --skip-ingest / --skip-open / --no-pause
REM ============================================================

cd /d "%~dp0"
start "qtf daily (safe-mode)" cmd /k _run_daily_inner.bat %*
exit /b 0
