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
	uvicorn app.main:app --reload

lint:
	ruff check app/ tests/

format:
	ruff format app/ tests/

coverage:
	pytest --cov=app --cov-report=term-missing tests/
