@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 用项目里的虚拟环境启动；/min 让黑色控制台窗口最小化（打包成 exe 后就没有了）
if exist ".venv\Scripts\python.exe" (
  start "Mini Cursor 后端" /min ".venv\Scripts\python.exe" app.py
) else (
  start "Mini Cursor 后端" /min python app.py
)
