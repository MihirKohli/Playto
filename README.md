# Playto — Merchant Payout Dashboard

A full-stack payout management system with a Django REST backend, React frontend, PostgreSQL database, and Celery workers for async payout processing.

## Architecture

| Service | Technology | Port |
|---|---|---|
| Backend API | Django + DRF + uvicorn | 8000 |
| Frontend | React 19 | 3000 |
| Database | PostgreSQL 15 | 5432 |
| Task queue | Celery + Redis | — |
| Broker/cache | Redis 7 | 6379 |

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose

That's it — everything else runs inside containers.

## Setup

### 1. Clone the repo

```bash
git clone <repo-url>
cd playto-playout
```

### 2. Create a `.env` file

Create a `.env` file in the project root. The backend reads these at startup:

```env
DATABASE_URL=postgresql://postgres:postgres@db:5432/payout

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=
```

> Leave `REDIS_PASSWORD` empty for local development. The services fall back to the defaults in `docker-compose.yml` if these variables are not set.

### 3. Start all services

```bash
docker compose up --build
```

This will:
1. Start PostgreSQL and Redis
2. Build and start the Django backend (runs `migrate` + `seed` automatically)
3. Start the Celery worker
4. Build and start the React frontend

### 4. Open the app

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API: [http://localhost:8000](http://localhost:8000)
- Django Admin: [http://localhost:8000/admin](http://localhost:8000/admin)

## Running without Docker

### Backend

```bash
cd payout-backend
python -m venv playto_env
source playto_env/bin/activate
pip install -r requirements.txt

# Set env vars or create a .env file in payout-backend/
python manage.py migrate
python manage.py seed
python manage.py runserver
```

In a separate terminal, start the Celery worker:

```bash
cd payout-backend
source playto_env/bin/activate
celery -A core worker -l info
```

### Frontend

```bash
cd payout-frontend
npm install
npm start
```

## Project structure

```
playto-playout/
├── docker-compose.yml
├── payout-backend/
│   ├── core/            # Django project settings, Celery config, URLs
│   ├── merchants/       # Merchant models, views, serializers
│   ├── payouts/         # Payout models, views, Celery tasks
│   ├── logs/            # DB-backed request/event logging
│   └── requirements.txt
└── payout-frontend/
    ├── src/
    │   ├── components/  # React components
    │   ├── App.js
    │   └── api.js       # API client
    └── package.json
```

## Environment variables reference

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Full PostgreSQL connection string | Falls back to `db:5432/payout` |
| `REDIS_HOST` | Redis hostname | `redis` |
| `REDIS_PORT` | Redis port | `6379` |
| `REDIS_PASSWORD` | Redis password | _(none)_ |
