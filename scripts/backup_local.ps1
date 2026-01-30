param(
    [string]$BackupRoot = "",
    [int]$RetentionDays = 30
)

$ErrorActionPreference = "Stop"

function Load-EnvFile {
    param([string]$Path)
    if (!(Test-Path $Path)) { return @{} }
    $vars = @{}
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line.Length -eq 0) { return }
        if ($line.StartsWith("#")) { return }
        $parts = $line.Split("=", 2)
        if ($parts.Count -ne 2) { return }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        $vars[$name] = $value
    }
    return $vars
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$envPath = Join-Path $repoRoot "server\.env"
$envVars = Load-EnvFile -Path $envPath

if ([string]::IsNullOrWhiteSpace($BackupRoot)) {
    $BackupRoot = Join-Path $repoRoot "backups"
}

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$pgFile = Join-Path $BackupRoot "postgres_$timestamp.dump"
$redisFile = Join-Path $BackupRoot "redis_$timestamp.rdb"

$postgresUser = $envVars["POSTGRES_USER"]
$postgresDb = $envVars["POSTGRES_DB"]
$postgresHost = $envVars["POSTGRES_HOST"]
$postgresPort = $envVars["POSTGRES_PORT"]
$postgresPassword = $envVars["POSTGRES_PASSWORD"]

$redisHost = $envVars["REDIS_HOST"]
$redisPort = $envVars["REDIS_PORT"]
$redisPassword = $envVars["REDIS_PASSWORD"]

$dockerNames = @()
try {
    $dockerNames = docker ps -a --format "{{.Names}}"
} catch {
    $dockerNames = @()
}

$hasPostgresContainer = $dockerNames -contains "inarbit-postgres"
$hasRedisContainer = $dockerNames -contains "inarbit-redis"

Write-Host "Backing up PostgreSQL..."
if ($hasPostgresContainer) {
    $tmpFile = "/tmp/inarbit_$timestamp.dump"
    docker exec inarbit-postgres pg_dump -U $postgresUser -d $postgresDb -F c -Z 6 -f $tmpFile | Out-Null
    docker cp "inarbit-postgres:$tmpFile" $pgFile | Out-Null
    docker exec inarbit-postgres rm -f $tmpFile | Out-Null
} else {
    if (Get-Command pg_dump -ErrorAction SilentlyContinue) {
        $env:PGPASSWORD = $postgresPassword
        pg_dump -h $postgresHost -p $postgresPort -U $postgresUser -d $postgresDb -F c -Z 6 -f $pgFile
        Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
    } else {
        Write-Host "pg_dump not found; skip PostgreSQL backup." -ForegroundColor Yellow
    }
}

Write-Host "Backing up Redis..."
if ($hasRedisContainer) {
    $tmpRdb = "/data/inarbit_$timestamp.rdb"
    $authArgs = @()
    if ($redisPassword) { $authArgs = @("-a", $redisPassword) }
    docker exec inarbit-redis redis-cli @authArgs --rdb $tmpRdb | Out-Null
    docker cp "inarbit-redis:$tmpRdb" $redisFile | Out-Null
    docker exec inarbit-redis rm -f $tmpRdb | Out-Null
} else {
    if (Get-Command redis-cli -ErrorAction SilentlyContinue) {
        $authArgs = @()
        if ($redisPassword) { $authArgs = @("-a", $redisPassword) }
        redis-cli -h $redisHost -p $redisPort @authArgs --rdb $redisFile | Out-Null
    } else {
        Write-Host "redis-cli not found; skip Redis backup." -ForegroundColor Yellow
    }
}

Write-Host "Cleaning old backups..."
$cutoff = (Get-Date).AddDays(-1 * $RetentionDays)
Get-ChildItem -Path $BackupRoot -File | Where-Object { $_.LastWriteTime -lt $cutoff } | ForEach-Object {
    Remove-Item $_.FullName -Force
}

Write-Host "Backup completed: $BackupRoot"
