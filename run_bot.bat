@echo off
echo ==============================================
echo AutoNewsBot - Daily Instagram Post Generator
echo ==============================================
cd /d "%~dp0"
python autonews.py
echo.
echo Operation Complete! Check the 'output' folder.
pause
