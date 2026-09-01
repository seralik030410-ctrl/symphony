@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL.ps1"
set "install_exit=%errorlevel%"
if not "%install_exit%"=="0" echo Runtime installation failed. Review the message above.
pause
exit /b %install_exit%
