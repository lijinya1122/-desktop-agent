@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在生成提交文件夹 MP2608016 ...
".venv\Scripts\python.exe" scripts\make_submission.py
echo.
echo 生成完毕，位置：%USERPROFILE%\Desktop\MP2608016
pause
