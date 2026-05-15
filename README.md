# beeplan-api

REST API для BeePlan: телеметрия с концентраторов, доменная модель, OpenAPI.

Архитектура и общие требования: репозиторий [**beeplan-docs**](https://github.com/beeplan/beeplan-docs) ([ARCHITECTURE.md](https://github.com/beeplan/beeplan-docs/blob/main/ARCHITECTURE.md)). Замените `github.com/beeplan`, если ваш org другой.

## Требования

- Python 3.9+
- Docker и Docker Compose (для PostgreSQL)

## Быстрый старт

Рекомендуется **Docker Compose** (Linux/macOS/WSL2; на Windows без MSVC так проще обойти сборку нативных колёс):

```powershell
cd beeplan-api
docker compose up --build
```

В другом терминале (на хосте с Python и доступом к БД на `localhost:5432`):

```powershell
cd beeplan-api
$env:PYTHONPATH = (Get-Location).Path
py -3 -m pip install -r requirements.txt   # на Windows может понадобиться MSVC Build Tools для greenlet
py -3 -m alembic upgrade head
py -3 -m beeplan.seed_dev
```

Если API запущен локально через `uvicorn`:

```powershell
$env:PYTHONPATH = (Get-Location).Path
py -3 -m uvicorn beeplan.main:app --reload --host 0.0.0.0 --port 8000
```

Скрипт `seed_dev` выведет URL API, учётные данные пользователя и **ingest_token** концентратора — сохраните его для `beeplan-gateway`.

- Документация интерактивно: http://localhost:8000/docs  
- OpenAPI YAML: [docs/openapi.yaml](docs/openapi.yaml)

## Переменные окружения

См. `.env.example`.

## Лицензия

MIT (при публикации добавьте файл `LICENSE`).
