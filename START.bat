@echo off
title Symphony 2.0 Launcher
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-all.ps1"
if errorlevel 1 (
  echo.
  echo Symphony could not start. See the message above.
  pause
)
