@echo off
title FinCtrl Launcher
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-all.ps1"
if errorlevel 1 (
  echo.
  echo FinCtrl could not start. See the message above.
  pause
)
