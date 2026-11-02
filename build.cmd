@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --windowed --onedir --name FormulaOCR --icon "formula_ocr\assets\formula-ocr.ico" --add-data "formula_ocr\assets:formula_ocr/assets" --collect-all latex2mathml --collect-data docx --hidden-import keyring.backends.Windows main.py
pause
