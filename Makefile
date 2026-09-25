.PHONY: build run dev logs install-dev test lint format

build:
	docker-compose build

run:
	docker-compose up -d

dev:
	uvicorn app.main:app --reload --port 8005

logs:
	docker-compose logs -f

install-dev:
	pip install -r requirements-dev.txt

# Needs a reachable Postgres (TEST_DATABASE_URL, default localhost:5432/farmer_registry_db).
# Tests create and drop their own schema; registry data is never touched.
test:
	pytest -q

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .
