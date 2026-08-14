param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw '未找到项目虚拟环境：.venv\Scripts\python.exe'
}

Push-Location $root
try {
    & $python -m pytest -q backend\tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($node) {
        & $node.Source --check frontend\static\script_enhanced.js
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } else {
        Write-Warning '未安装 Node.js，跳过前端 JavaScript 语法检查。'
    }
} finally {
    Pop-Location
}
