@echo off
rem يوقف البوت وحلقة إعادة التشغيل
wmic process where "CommandLine like '%%run_bot.bat%%'" call terminate >nul 2>&1
wmic process where "CommandLine like '%%bot.py%%' and Name='python.exe'" call terminate >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run_bot.bat*' -or ($_.Name -eq 'python.exe' -and $_.CommandLine -like '*bot.py*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Bot stopped.
