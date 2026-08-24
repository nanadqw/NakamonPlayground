@echo off
rem column_src.txt から column.html を作り直す（ダブルクリックで実行できます）
cd /d "%~dp0"
python build_column.py
echo.
pause
