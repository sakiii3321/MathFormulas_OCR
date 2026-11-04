@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install -r requirements-webview2.txt pyinstaller
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm --windowed --onefile --name FormulaOCR-WebView2 --distpath dist\webview2 --workpath build\webview2 --icon "formula_ocr\assets\formula-ocr.ico" --version-file "packaging\windows-version.txt" --add-data "LICENSE:." --add-data "formula_ocr\assets:formula_ocr/assets" --collect-all latex2mathml --collect-data docx --collect-all sideview --copy-metadata sideview --hidden-import keyring.backends.Windows --exclude-module formula_ocr.qt_preview --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtWebEngineQuick main_webview2.py
exit /b %ERRORLEVEL%
