@echo off
chcp 65001 >nul
if not exist "%~dp0.venv\Scripts\pythonw.exe" (echo Lance d'abord INSTALLER_WINDOWS.bat & pause & exit /b 1)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0scripts\desktop.py" %*
