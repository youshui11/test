# 文件作用：在本机 PostgreSQL 目标库中启用 pgvector 扩展，交互输入超级用户密码。
# 关联关系：属于显式环境准备工具；网站向量检索依赖该扩展。
# 用途：由用户在本机输入 PostgreSQL 超级用户密码，为 wendang 启用向量扩展。
$ErrorActionPreference = 'Stop'
$psqlPath = 'C:\Program Files\PostgreSQL\17\bin\psql.exe'
if (-not (Test-Path -LiteralPath $psqlPath)) {
    $psqlPath = (Get-Command psql -ErrorAction Stop).Source
}
Write-Host 'Enable pgvector in database wendang. Enter your PostgreSQL postgres password when prompted.'
Write-Host 'The password is handled by psql locally and is not saved by this script.'
& $psqlPath -X -W -h localhost -p 5432 -U postgres -d wendang -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector;'
$setupExit = $LASTEXITCODE
if ($setupExit -eq 0) {
    Write-Host 'pgvector enabled. You can return to Codex.' -ForegroundColor Green
} else {
    Write-Host 'Setup failed. Check the postgres password or database privileges.' -ForegroundColor Red
}
Read-Host 'Press Enter to close'
exit $setupExit
