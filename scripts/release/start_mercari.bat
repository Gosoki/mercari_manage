@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "mercari-server.exe" (
  echo [错误] 当前目录下未找到 mercari-server.exe
  pause
  exit /b 1
)

set "PORT=%MERCARI_PORT%"
if "%PORT%"=="" set "PORT=9601"
set "MERCARI_PORT=%PORT%"

echo ========================================
echo   mercari 订单管理 — 启动服务并打开浏览器
echo   端口: %PORT% ^(可通过环境变量 MERCARI_PORT 修改^)
echo ========================================
echo.

start "mercari-server" "%~dp0mercari-server.exe"

echo 等待后端就绪...
set /a _n=0
:wait_health
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/api/health' -UseBasicParsing -TimeoutSec 2; exit ([int]($r.StatusCode -ne 200)) } catch { exit 1 }" 2>nul
if %errorlevel% equ 0 goto open_browser
set /a _n+=1
if %_n% geq 60 (
  echo [警告] 等待超时，仍将尝试打开浏览器。若页面无法加载，请查看 mercari-server 窗口日志。
  goto open_browser
)
timeout /t 1 /nobreak >nul
goto wait_health

:open_browser
start "" "http://127.0.0.1:%PORT%/launcher.html"
echo.
echo 已请求打开浏览器。服务窗口保持运行，关闭该窗口即停止后端。
echo.
pause
