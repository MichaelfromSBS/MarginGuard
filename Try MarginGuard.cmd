@echo off
cd /d "%~dp0"
python scripts/demo.py
if errorlevel 1 pause
