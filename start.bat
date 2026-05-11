@echo off
chcp 65001 >nul
echo ========================================
echo   mercari 订单管理 启动脚本
echo ========================================
echo.

set ROOT=%~dp0
set BACKEND=%ROOT%backend
set WEBSIDE=%ROOT%webside

echo [1/2] 激活 conda 环境 mercari 并启动后端...
call conda activate mercari

cd /d %BACKEND%
start /b python -m uvicorn main:app --host 0.0.0.0 --port 9601

timeout /t 2 /nobreak >nul

echo [2/2] 初始化前端依赖并启动...
where node >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 Node.js，请先安装并加入 PATH: https://nodejs.org/
  pause
  exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 npm，请检查 Node.js 安装是否完整
  pause
  exit /b 1
)

cd /d %WEBSIDE%
call npm install
if errorlevel 1 (
  echo [错误] npm install 失败，请检查网络与 package.json
  pause
  exit /b 1
)

echo.
echo ========================================
echo   前端:      http://localhost:9600  ^(或本机域名 / IP:9600^)
echo   后端 API:  http://localhost:9601  ^(或本机 IP:9601^)
echo   API 文档:  http://localhost:9601/docs
echo   按 Ctrl+C 停止
echo ========================================
echo.

npm run dev
