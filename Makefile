.PHONY: build up down logs test dev

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --rm backend pytest tests/ -v

dev:
	uvicorn app.main:app --reload
