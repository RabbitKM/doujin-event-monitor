@echo off
REM 開拓動漫祭 報名監控 - 啟動腳本
REM 請先設定好 FF_DISCORD_WEBHOOK 環境變數

cd /d "%~dp0"
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
"C:\Users\a0506\AppData\Local\Programs\Python\Python312\python.exe" monitor.py >> logs\monitor.log 2>&1
