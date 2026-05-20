@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "mercari-server.exe" (
  echo [错误] 当前目录下未找到 mercari-server.exe
  echo 请将本脚本放在与 mercari-server.exe 相同的发布目录中运行。
  pause
  exit /b 1
)

set "PORT=%MERCARI_PORT%"
if "%PORT%"=="" set "PORT=9601"
set "MERCARI_PORT=%PORT%"

echo ========================================
echo   mercari 订单管理 — 重启系统
echo   端口: %PORT% ^(环境变量 MERCARI_PORT 可修改^)
echo ========================================
echo.

echo [1/3] 正在停止 mercari-server...
taskkill /IM mercari-server.exe /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq mercari-server*" /F >nul 2>&1

echo [2/3] 等待服务退出...
set /a _n=0
:wait_down
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/api/health' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" 2>nul
if %errorlevel% neq 0 goto start_server
set /a _n+=1
if %_n% geq 30 goto force_wait
timeout /t 1 /nobreak >nul
goto wait_down

:force_wait
timeout /t 2 /nobreak >nul

:start_server
echo [3/3] 正在启动 mercari-server...
start "mercari-server" "%~dp0mercari-server.exe"

echo 等待后端就绪...
set /a _n=0
:wait_health
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/api/health' -UseBasicParsing -TimeoutSec 2; exit ([int]($r.StatusCode -ne 200)) } catch { exit 1 }" 2>nul
if %errorlevel% equ 0 goto done
set /a _n+=1
if %_n% geq 90 (
  echo [警告] 健康检查超时，请查看 mercari-server 窗口日志。
  goto done
)
timeout /t 1 /nobreak >nul
goto wait_health

:done
echo.
echo 重启完成。访问: http://127.0.0.1:%PORT%/
echo.
pause
