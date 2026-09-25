.PHONY: build run dev logs

build:
	docker-compose build

run:
	docker-compose up -d

dev:
	uvicorn app.main:app --reload --port 8005

logs:
	docker-compose logs -f
