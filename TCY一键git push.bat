@echo off
chcp 65001 >nul
title Git 一键同步工具
color 0A

echo ========================================================
echo       Git 一键同步脚本 (通用版)
echo ========================================================
echo.

:: 1. 获取提交注释
set /p commit_msg=请输入本次更新的内容(注释): 
if "%commit_msg%"=="" set commit_msg=日常维护更新

echo.
echo [1/3] 正在执行 git add ...
git add .
if %errorlevel% neq 0 goto :Error

echo.
echo [2/3] 正在执行 git commit ...
git commit -m "%commit_msg%"
:: 即使 commit 报错（通常是因为没有文件变动），我们也允许它继续尝试 push
if %errorlevel% neq 0 (
    echo [提示] 似乎没有文件需要提交，或者 commit 出错了。
    echo 正在尝试继续执行推送...
)

echo.
echo [3/3] 正在推送到远程仓库 ...
git push
if %errorlevel% neq 0 goto :Error

echo.
echo ========================================================
echo               🎉 恭喜！代码已成功同步到远程仓库！
echo ========================================================
pause
exit

:Error
color 0C
echo.
echo ========================================================
echo               ❌ 错误！脚本已停止运行！
echo ========================================================
echo 请检查上方的错误信息（通常是网络问题或需要先 git pull）。
pause
exit