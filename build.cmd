@echo off
setlocal
cd /d "%~dp0"
set "LAYOUT=--onedir"
if /I "%~1"=="onefile" set "LAYOUT=--onefile"
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --windowed %LAYOUT% --name FormulaOCR --icon "formula_ocr\assets\formula-ocr.ico" --version-file "packaging\windows-version.txt" --add-data "LICENSE:." --add-data "formula_ocr\assets:formula_ocr/assets" --collect-all latex2mathml --collect-data docx --hidden-import keyring.backends.Windows --exclude-module formula_ocr.webview2_preview --exclude-module sideview main.py
exit /b %ERRORLEVEL%
