@echo off
setlocal

rem Starts the CARLA AV client, the CARLA co-sim plugin and the UDP bridge,
rem each in its own window. Run from anywhere; paths are relative to this file.

set "ROOT=%~dp0"
set "PYTHON=%ROOT%venv\Scripts\python.exe"

if not exist "%ROOT%.env" (
    echo .env not found in %ROOT%. Copy .env.example to .env and fill it in.
    exit /b 1
)
if not exist "%PYTHON%" (
    echo %PYTHON% not found. Create the venv and run "pip install -e ." first.
    exit /b 1
)

rem Load .env into this session. The windows started below inherit it.
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%ROOT%.env") do set "%%a=%%b"

cd /d "%ROOT%"

echo Starting carla_av_simple.py (spawns the CAV)...
start "carla_av_simple" cmd /k ""%PYTHON%" examples\carla_examples\carla_av_simple.py"

rem Give the AV client time to spawn the CAV before the co-sim plugin looks for it.
timeout /t 5 /nobreak >nul

echo Starting carla_cosim_simple.py (writes cav_info to Redis)...
start "carla_cosim_simple" cmd /k ""%PYTHON%" examples\carla_examples\carla_cosim_simple.py"

echo Starting run_udp_bridge.py...
start "run_udp_bridge" cmd /k ""%PYTHON%" examples\udp_examples\run_udp_bridge.py"

echo All three started. Close each window (or press Ctrl+C in it) to stop it.
endlocal
