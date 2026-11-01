@echo off
chcp 65001 >nul
echo === Installation de Phenix-video ===
where python >nul 2>nul || (echo Python manquant. Installe-le : winget install Python.Python.3.12 & pause & exit /b 1)
where ffmpeg >nul 2>nul || (echo Installation de FFmpeg... & winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements)
python -m venv "%~dp0.venv" || (echo Echec creation venv & pause & exit /b 1)
call "%~dp0.venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install --default-timeout=120 -r "%~dp0requirements.txt" || (echo Echec pip & pause & exit /b 1)
echo Fenetre native (facultatif)...
python -m pip install --default-timeout=120 pywebview >nul 2>nul
echo Creation des raccourcis (Bureau et menu Demarrer)...
powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell; foreach($d in @([Environment]::GetFolderPath('Desktop'),(Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'))){ $l=$w.CreateShortcut((Join-Path $d 'Phenix-video.lnk')); $l.TargetPath='%~dp0LANCER_WINDOWS.bat'; $l.WorkingDirectory='%~dp0'; $l.IconLocation='%~dp0assets\icon.ico'; $l.WindowStyle=7; $l.Save() }"
echo.
echo Installation terminee. Double-clique sur le raccourci Phenix-video du Bureau.
echo (si FFmpeg vient d'etre installe, ferme et rouvre une fenetre avant de lancer)
pause
