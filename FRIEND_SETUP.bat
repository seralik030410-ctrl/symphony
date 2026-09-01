@echo off
title Symphony 2.0 - First setup
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\friend-setup.ps1"
if errorlevel 1 (
  echo.
  echo Setup did not finish. Read the message above, then run FRIEND_SETUP.bat again.
  pause
)
