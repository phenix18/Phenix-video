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
echo.
echo Installation terminee. Ferme cette fenetre, puis double-clique sur LANCER_WINDOWS.bat
echo (si FFmpeg vient d'etre installe, ferme et rouvre une fenetre avant de lancer)
pause
