@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
:loop
echo [%date% %time%] Starting bot... >> bot.log
"C:\Python314\python.exe" -u bot.py >> bot.log 2>&1
echo [%date% %time%] Bot stopped, restarting in 30 seconds... >> bot.log
timeout /t 30 /nobreak >nul
goto loop
