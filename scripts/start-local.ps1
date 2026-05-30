# Локальный запуск API (без Docker для самого API).
# Вариант A: PostgreSQL в Docker на порту 5433 (нужен Docker Desktop).
# Вариант B: своя БД — задайте DATABASE_URL в .env и выполните setup_local_db.py с POSTGRES_PASSWORD.

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

$useDockerDb = $env:BEEPLAN_USE_DOCKER_DB -ne "0"
if ($useDockerDb) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "Docker не найден. Установите Docker Desktop или задайте DATABASE_URL в .env и BEEPLAN_USE_DOCKER_DB=0"
        exit 1
    }
    docker compose -f docker-compose.dev.yml up -d
    $env:DATABASE_URL = "postgresql+psycopg2://beeplan:beeplan@localhost:5433/beeplan"
    Write-Host "Waiting for PostgreSQL on :5433..."
    Start-Sleep -Seconds 5
} else {
    if (-not $env:DATABASE_URL) {
        $env:DATABASE_URL = "postgresql+psycopg2://beeplan:beeplan@localhost:5432/beeplan"
    }
}

$env:PYTHONPATH = $Root
$env:JWT_SECRET = "dev-secret-change-in-production"

py -3 -m alembic upgrade head
py -3 -m beeplan.seed_dev

Write-Host ""
Write-Host "Starting API at http://localhost:8000 (docs: /docs)"
py -3 -m uvicorn beeplan.main:app --reload --host 0.0.0.0 --port 8000
