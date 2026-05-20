@echo off
chcp 65001 >nul
echo ========================================
echo   mercari 打包 ^(PyInstaller + 前端 build^)
echo ========================================
echo.

set ROOT=%~dp0
cd /d "%ROOT%"

:: 版本号（发布前修改）
set VERSION=v1.0.0

:: 同步版本到 webside\package.json
echo 同步版本到 webside\package.json...
set VERSION_NUM=%VERSION%
if "%VERSION_NUM:~0,1%"=="v" set VERSION_NUM=%VERSION_NUM:~1%
set TEMP_PS=%TEMP%\mercari_sync_version.ps1
echo $filePath = Join-Path '%ROOT%webside' 'package.json' > "%TEMP_PS%"
echo $content = [System.IO.File]::ReadAllText($filePath, [System.Text.Encoding]::UTF8) >> "%TEMP_PS%"
echo $content = $content -replace '^\uFEFF', '' >> "%TEMP_PS%"
echo $oldVersion = 'unknown' >> "%TEMP_PS%"
echo if ($content -match '"version"\s*:\s*"([^"]+)"'^) { $oldVersion = $matches[1] } >> "%TEMP_PS%"
echo $content = [regex]::Replace($content, '"version"\s*:\s*"([^"]+)"', '"version": "%VERSION_NUM%"') >> "%TEMP_PS%"
echo $Utf8NoBomEncoding = New-Object System.Text.UTF8Encoding $False >> "%TEMP_PS%"
echo [System.IO.File]::WriteAllText($filePath, $content, $Utf8NoBomEncoding) >> "%TEMP_PS%"
echo Write-Host "Version synced: $oldVersion -^> %VERSION_NUM%" >> "%TEMP_PS%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP_PS%"
if %errorlevel% neq 0 (
    echo [警告] 同步 package.json 版本失败，可手动检查 webside\package.json
) else (
    echo 已同步版本。
)
del "%TEMP_PS%" >nul 2>&1

call conda activate mercari
if %errorlevel% neq 0 (
    echo [错误] 无法激活 conda 环境 mercari，请先创建并安装 backend\requirements.txt
    pause
    exit /b 1
)

if not exist "Releases" mkdir Releases
if not exist "Releases\%VERSION%" mkdir "Releases\%VERSION%"
echo 输出目录: Releases\%VERSION%
echo.

echo 清理旧构建...
if exist "backend\dist" rmdir /s /q "backend\dist"
if exist "backend\build" rmdir /s /q "backend\build"

echo.
echo [1/4] PyInstaller 打包 mercari-server.exe...
cd /d "%ROOT%backend"
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [提示] 当前 conda 环境未安装 PyInstaller，正在 pip install...
    pip install pyinstaller
)
python -m PyInstaller mercari.spec --clean --noconfirm --distpath "%ROOT%Releases\%VERSION%"
if %errorlevel% neq 0 (
    echo [错误] PyInstaller 失败。若缺模块，请编辑 backend\mercari.spec 的 collect_all / hiddenimports。
    cd /d "%ROOT%"
    pause
    exit /b 1
)
cd /d "%ROOT%"

echo.
echo [2/4] 构建前端 production...
cd /d "%ROOT%webside"
if not exist "node_modules" (
    echo 安装前端依赖...
    call npm install
    if %errorlevel% neq 0 (
        echo [错误] npm install 失败
        cd /d "%ROOT%"
        pause
        exit /b 1
    )
)
call npm run build
if %errorlevel% neq 0 (
    echo [错误] npm run build 失败
    cd /d "%ROOT%"
    pause
    exit /b 1
)
cd /d "%ROOT%"

echo.
echo [3/4] 复制前端 dist 与启动脚本...
if not exist "webside\dist" (
    echo [错误] 未找到 webside\dist
    pause
    exit /b 1
)
if not exist "Releases\%VERSION%\webside" mkdir "Releases\%VERSION%\webside"
xcopy "webside\dist" "Releases\%VERSION%\webside\dist\" /E /I /H /Y /Q

copy /y "scripts\release\start_mercari.bat" "Releases\%VERSION%\start_mercari.bat" >nul
if %errorlevel% neq 0 (
    echo [警告] 未复制 start_mercari.bat ^(请确认存在 scripts\release\start_mercari.bat^)
) else (
    echo - start_mercari.bat 已复制
)

copy /y "scripts\release\restart.bat" "Releases\%VERSION%\restart.bat" >nul
if %errorlevel% neq 0 (
    echo [警告] 未复制 restart.bat ^(请确认存在 scripts\release\restart.bat^)
) else (
    echo - restart.bat 已复制
)

if not exist "Releases\%VERSION%\log" mkdir "Releases\%VERSION%\log"

echo.
echo [4/4] 清理 backend 中间产物 ^(保留 mercari.spec^)...
if exist "backend\build" rmdir /s /q "backend\build"

echo.
echo 打包完成: Releases\%VERSION%
dir /b "Releases\%VERSION%\*.exe" 2>nul

set ZIP_FILE=%ROOT%Releases\mercari-%VERSION_NUM%.zip
if exist "%ZIP_FILE%" del /q "%ZIP_FILE%"
echo.
echo 正在生成 ZIP: %ZIP_FILE%
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%ROOT%Releases\%VERSION%\*' -DestinationPath '%ZIP_FILE%' -CompressionLevel Optimal -Force"
if %errorlevel% neq 0 (
    echo [警告] ZIP 创建失败
) else (
    echo ZIP 已生成。
)

echo.
echo ========================================
echo 发布目录结构与使用说明
echo ========================================
echo - mercari-server.exe 与 webside\dist 须在同一发布目录 ^(本脚本已复制^)。
echo - 用户双击 start_mercari.bat：启动服务并打开 launcher 页面。
echo - 开发调试不加静态页时: set MERCARI_NO_STATIC=1
echo ========================================
pause
