@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM  qtf one-click runner -- complete the full daily cycle.
REM
REM  Default flow: env probe -> ingest -> execute -> open report
REM
REM  Options (stackable, order doesn't matter):
REM    --dry-run       plan orders but don't submit
REM    --retrain       retrain LightGBM model before executing
REM    --skip-ingest   skip data pull (if already done today)
REM    --skip-open     do NOT auto-open the report
REM    --no-pause      no pause at end (scheduled task / CI mode)
REM
REM  Each Python step's stderr is captured to logs\<step>_stderr.log so a
REM  silent crash leaves a readable trace even if the cmd window closes.
REM ============================================================

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

if "%QTF_PYTHON%"=="" (
    set "PY=C:\Users\gjq00\.conda\envs\qtf\python.exe"
) else (
    set "PY=%QTF_PYTHON%"
)

set "SKILL_DIR=C:\Users\gjq00\.claude\skills\moomooapi"
set "LOGDIR=%PROJECT_DIR%\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

set "DRY_RUN_FLAG="
set "RETRAIN=0"
set "SKIP_INGEST=0"
set "SKIP_OPEN=0"
set "NO_PAUSE=0"

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--dry-run" set "DRY_RUN_FLAG=--dry-run"
if /i "%~1"=="--retrain" set "RETRAIN=1"
if /i "%~1"=="--skip-ingest" set "SKIP_INGEST=1"
if /i "%~1"=="--skip-open" set "SKIP_OPEN=1"
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"
shift
goto parse_args
:args_done

cd /d "%PROJECT_DIR%"

REM Today's date (yyyy-mm-dd, locale-safe via Python).
for /f "usebackq delims=" %%I in (`"%PY%" -c "import datetime; print(datetime.date.today().isoformat())" 2^>nul`) do set "TODAY=%%I"
if "%TODAY%"=="" set "TODAY=unknown"

echo.
echo ============================================================
echo  qtf daily trading cycle  --  %TODAY%
echo  Project:  %PROJECT_DIR%
echo  Python:   %PY%
echo  Log dir:  %LOGDIR%
if not "%DRY_RUN_FLAG%"=="" echo  Mode:     DRY-RUN (no real orders)
if "%RETRAIN%"=="1" echo  Extra:    retrain model
if "%SKIP_INGEST%"=="1" echo  Extra:    skip data ingest
echo ============================================================

if not exist "%PY%" (
    echo.
    echo [FATAL] qtf env Python not found: %PY%
    echo         Run: conda create -n qtf python=3.11
    echo         Or override: set QTF_PYTHON=C:\path\to\python.exe
    set "LAST_STEP=python-check"
    goto end_failure
)

REM Step 1: probe OpenD
echo.
echo ---- Step 1/4: probe OpenD ----
set "STEP_LOG=%LOGDIR%\01_probe_stderr.log"
"%PY%" "%SKILL_DIR%\scripts\check_env.py" > "%STEP_LOG%" 2>&1
set "STEP_RC=%errorlevel%"
type "%STEP_LOG%"
if not "%STEP_RC%"=="0" (
    echo.
    echo [FATAL] OpenD probe failed [exit=%STEP_RC%]. Output above.
    set "LAST_STEP=probe-opend"
    goto end_failure
)

REM Step 2: ingest
if "%SKIP_INGEST%"=="0" (
    echo.
    echo ---- Step 2/4: ingest daily K-line ----
    set "STEP_LOG=%LOGDIR%\02_ingest_stderr.log"
    "%PY%" scripts\01_ingest.py --years 5 > "!STEP_LOG!" 2>&1
    set "STEP_RC=!errorlevel!"
    type "!STEP_LOG!"
    if not "!STEP_RC!"=="0" (
        echo.
        echo [FATAL] data ingest failed [exit=!STEP_RC!]. Output above.
        set "LAST_STEP=ingest"
        goto end_failure
    )
) else (
    echo.
    echo ---- Step 2/4: skip data ingest ----
)

REM Step 3: optional retrain
if "%RETRAIN%"=="1" (
    echo.
    echo ---- Step 3/4: retrain LightGBM + Alpha158 ----
    set "STEP_LOG=%LOGDIR%\03_train_stderr.log"
    "%PY%" scripts\02_train.py > "!STEP_LOG!" 2>&1
    set "STEP_RC=!errorlevel!"
    type "!STEP_LOG!"
    if not "!STEP_RC!"=="0" (
        echo.
        echo [FATAL] training failed [exit=!STEP_RC!]. Output above.
        set "LAST_STEP=train"
        goto end_failure
    )
) else (
    echo.
    echo ---- Step 3/4: skip training [using existing model] ----
)

REM Step 4: execute (predict + risk + submit + report)
echo.
echo ---- Step 4/4: execute -- predict / risk / submit / report ----
set "STEP_LOG=%LOGDIR%\04_execute_stderr.log"
"%PY%" scripts\04_execute.py %DRY_RUN_FLAG% > "%STEP_LOG%" 2>&1
set "EXEC_RC=%errorlevel%"
type "%STEP_LOG%"
if not "%EXEC_RC%"=="0" (
    echo.
    echo [WARN] 04_execute.py exit=%EXEC_RC%. Output above. Log: %STEP_LOG%
)

REM Final summary -- always shown
set "REPORT=%PROJECT_DIR%\reports\%TODAY%.md"
set "SNAPSHOT=%PROJECT_DIR%\data\snapshots\equity_history.csv"
set "JSONL=%LOGDIR%\qtf.jsonl"

echo.
echo ============================================================
echo  Summary
echo ============================================================
if exist "%REPORT%" (
    echo   [OK]   Report:    %REPORT%
) else (
    echo   [MISS] Report:    %REPORT%   [not generated]
)
if exist "%SNAPSHOT%" (
    echo   [OK]   Snapshot:  %SNAPSHOT%
) else (
    echo   [MISS] Snapshot:  %SNAPSHOT%
)
echo          Step logs: %LOGDIR%\0[1-4]_*_stderr.log
echo          JSON log:  %JSONL%
echo ============================================================

if exist "%REPORT%" if "%SKIP_OPEN%"=="0" start "" "%REPORT%"

if not "%EXEC_RC%"=="0" goto end_warning
goto end_success

:end_success
echo.
echo  [OK] all done.
echo.
if not "%NO_PAUSE%"=="1" pause
endlocal
exit /b 0

:end_warning
echo.
echo  [DONE WITH WARNINGS] 04_execute exit=%EXEC_RC% -- see stderr above and %JSONL%
echo.
if not "%NO_PAUSE%"=="1" pause
endlocal
exit /b %EXEC_RC%

:end_failure
echo.
echo  [FAILED at step: %LAST_STEP%] -- see stderr above and %JSONL%
echo.
if not "%NO_PAUSE%"=="1" pause
endlocal
exit /b 1
