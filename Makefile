.PHONY: build up down logs test dev lint format coverage

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
	uvicorn backend.main:app --reload

lint:
	ruff check backend/ tests/

format:
	ruff format backend/ tests/

coverage:
	pytest --cov=backend --cov-report=term-missing tests/
