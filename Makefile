.PHONY: help up down logs seed test smoke dev-api dev-web build-web install clean \
        up-nas down-nas logs-nas doctor backup build-arm

# каталог данных на Synology (переопределяется в .env проекта)
DATA_ROOT ?= /volume1/docker/schoolhub
COMPOSE_NAS := docker compose -f deploy/synology/docker-compose.yml --env-file $(DATA_ROOT)/.env

help: ## Показать справку
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- локальная разработка
up: ## Поднять dev-стенд в Docker (Postgres + API + Vite)
	docker compose up --build -d
	@echo "Frontend: http://localhost:5173  |  API docs: http://localhost:8000/docs"

down: ## Остановить dev-стенд
	docker compose down

logs: ## Логи backend'а (dev)
	docker compose logs -f backend

seed: ## (Пере)засеять демо-данные
	cd backend && python -m scripts.seed --force

test: ## Интеграционные тесты backend'а (104)
	cd backend && python -m pytest -q

smoke: ## Сквозной smoke-тест всех сценариев (151 проверка)
	cd backend && python scripts/smoke_test.py

migrate: ## Применить миграции схемы (alembic upgrade head)
	cd backend && alembic upgrade head

revision: ## Создать миграцию: make revision m="описание изменения"
	cd backend && alembic revision --autogenerate -m "$(m)"

dev-api: ## Backend с автоперезагрузкой
	cd backend && uvicorn app.main:app --reload --port 8000

dev-web: ## Frontend dev server
	cd frontend && npm run dev

build-web: ## Production-сборка фронтенда
	cd frontend && npm run build

install: ## Установить зависимости локально
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

# ---------------------------------------------------------------- Synology NAS (arm64)
up-nas: ## Собрать и запустить SchoolHub на NAS (deploy/synology)
	$(COMPOSE_NAS) up -d --build
	@$(MAKE) --no-print-directory doctor

down-nas: ## Остановить стек на NAS
	$(COMPOSE_NAS) down

logs-nas: ## Логи backend'а на NAS
	docker logs -f schoolhub-backend

doctor: ## Диагностика развёртывания: контейнеры, БД, LDAP, память, место
	bash deploy/synology/check-health.sh

backup: ## Бэкап БД (pg_dump + sha256 + ротация)
	bash deploy/synology/backup-db.sh

build-arm: ## Проверить сборку образов под linux/arm64 на x86-машине (buildx/qemu)
	docker buildx build --platform linux/arm64 -t schoolhub-backend:arm64-test backend
	docker buildx build --platform linux/arm64 --target prod -t schoolhub-frontend:arm64-test frontend

clean: ## Удалить артефакты сборки
	rm -rf frontend/dist backend/.pytest_cache frontend/tsconfig.tsbuildinfo
	find . -type d -name __pycache__ -not -path "*/node_modules/*" -exec rm -rf {} +
