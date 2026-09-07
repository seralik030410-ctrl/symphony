@echo off
title FinCtrl - API setup
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configure-api.ps1"
echo.
pause
