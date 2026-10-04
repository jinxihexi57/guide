# 设置脚本所在目录为工作目录
$scriptPath = $MyInvocation.MyCommand.Definition
$scriptDir = Split-Path -Parent $scriptPath
Set-Location $scriptDir

Write-Host "============================================" -ForegroundColor Green
Write-Host "旅行规划AI助手 - 前后端启动脚本" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green

# 检查npm是否安装
try {
    $npmVersion = npm --version
    Write-Host "npm版本: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "错误: npm未安装，请先安装Node.js" -ForegroundColor Red
    Read-Host "按任意键退出..."
    exit 1
}

# 检查Python是否安装
try {
    $pythonVersion = python --version
    Write-Host "Python版本: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "错误: Python未安装，请先安装Python" -ForegroundColor Red
    Read-Host "按任意键退出..."
    exit 1
}

# 安装项目依赖
Write-Host "正在安装项目依赖..." -ForegroundColor Yellow
npm install

if ($LASTEXITCODE -ne 0) {
    Write-Host "依赖安装失败" -ForegroundColor Red
    Read-Host "按任意键退出..."
    exit 1
}

Write-Host "依赖安装成功" -ForegroundColor Green

# 安装前端依赖
Write-Host "正在安装前端依赖..." -ForegroundColor Yellow
Set-Location frontend
npm install

if ($LASTEXITCODE -ne 0) {
    Write-Host "前端依赖安装失败" -ForegroundColor Red
    Read-Host "按任意键退出..."
    exit 1
}

Write-Host "前端依赖安装成功" -ForegroundColor Green
Set-Location ..

# 启动前后端
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "正在启动前后端服务..." -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "后端服务: http://localhost:8000" -ForegroundColor Yellow
Write-Host "前端服务: http://localhost:5173" -ForegroundColor Yellow
Write-Host "按 Ctrl+C 停止服务" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan

# 使用concurrently启动前后端
npm run dev
