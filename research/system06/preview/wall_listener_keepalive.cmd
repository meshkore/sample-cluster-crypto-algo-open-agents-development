@echo off
REM Keep the MeshKore Wall listener alive. No privileges, no service, no elevation.
REM
REM WHY: the listener died on 2026-09-11 at 18:16 and was not noticed until 2026-09-13 at
REM 16:10. For two days this agent appeared connected to anyone who asked the cluster and
REM was not there. The listener already reconnects forever through network failures - what
REM it cannot survive is its own process being killed, which is exactly how it died.
REM
REM Scheduled Task registration needs elevation on this machine, so this wrapper goes in
REM the per-user Startup folder instead: it starts at log-on with the user's own rights,
REM which is all a tokenless public-cluster reader should ever have.
REM REPO is written as an ABSOLUTE path when this file is installed into the Startup
REM folder, because %~dp0 there points at the Startup folder and not at the repository.
REM That is a real bug this script had for exactly one attempt.
setlocal
set REPO=__REPO__
cd /d "%REPO%"
:loop
python -u research\system06\preview\wall_listener.py >> research\system06\wall_listener.out 2>&1
REM A clean exit is still an exit: nothing about this daemon is supposed to finish.
timeout /t 10 /nobreak >nul
goto loop
