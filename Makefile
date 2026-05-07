.PHONY: help up down logs ps build rebuild migrate psql shell-api shell-scraper test fmt

help:
	@echo "Beacon Screener — common commands"
	@echo "  make up         start stack (detached)"
	@echo "  make down       stop stack"
	@echo "  make logs       tail all service logs"
	@echo "  make ps         show running services"
	@echo "  make build      build all images"
	@echo "  make rebuild    rebuild without cache"
	@echo "  make migrate    apply db/migrations to PostgreSQL"
	@echo "  make psql       open psql prompt to the database"
	@echo "  make shell-api      shell into the api container"
	@echo "  make shell-scraper  shell into the scraper container"
	@echo "  make scrape     trigger an immediate full scrape (requires admin)"
	@echo "  make score      trigger an immediate scoring run"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

build:
	docker compose build

rebuild:
	docker compose build --no-cache

migrate:
	@if [ -z "$$DB_PASSWORD" ]; then \
		set -a; . ./.env; set +a; \
	fi; \
	for f in db/migrations/*.sql; do \
		echo ">> Applying $$f"; \
		PGPASSWORD=$$DB_PASSWORD psql -h $$DB_HOST -p $$DB_PORT -U $$DB_USER -d $$DB_NAME -f $$f; \
	done

psql:
	@set -a; . ./.env; set +a; \
	PGPASSWORD=$$DB_PASSWORD psql -h $$DB_HOST -p $$DB_PORT -U $$DB_USER -d $$DB_NAME

shell-api:
	docker compose exec api /bin/bash

shell-scraper:
	docker compose exec scraper /bin/bash

scrape:
	docker compose exec scraper curl -fsS -X POST http://localhost:8001/scrape/all

score:
	docker compose exec recommender curl -fsS -X POST http://localhost:8002/score/all/sync

fmt:
	docker compose run --rm api ruff format /app
