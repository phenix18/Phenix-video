@echo off
chcp 65001 >nul
call "%~dp0.venv\Scripts\activate.bat" || (echo Lance d'abord INSTALLER_WINDOWS.bat & pause & exit /b 1)
python "%~dp0scripts\app.py"
pause
