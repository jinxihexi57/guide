@echo off
chcp 65001 >nul
echo ============================================
echo 旅行规划AI助手 - 前后端启动脚本
echo ============================================
echo.

echo 检查项目依赖...
if not exist "node_modules" (
    echo 正在安装项目依赖...
    npm install
    if %errorlevel% neq 0 (
        echo 依赖安装失败
        pause
        exit /b 1
    )
    echo 依赖安装成功
) else (
    echo 项目依赖已安装
)
echo.

echo 检查前端依赖...
cd frontend
if not exist "node_modules" (
    echo 正在安装前端依赖...
    npm install
    if %errorlevel% neq 0 (
        echo 前端依赖安装失败
        pause
        exit /b 1
    )
    echo 前端依赖安装成功
) else (
    echo 前端依赖已安装
)
cd ..
echo.

echo ============================================
echo 正在启动前后端服务...
echo ============================================
echo 后端服务: http://localhost:8000
echo 前端服务: http://localhost:5173
echo.
echo 按 Ctrl+C 停止服务
echo ============================================
echo.

npm run dev

pause
