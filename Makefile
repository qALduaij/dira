.PHONY: start live test services services-mac docker
start:
	bash scripts/start.sh
live:
	bash scripts/start-live.sh
test:
	uv run pytest -q
	npm --prefix frontend test
	npm --prefix frontend run build
services:
	docker compose up -d qdrant mediamtx
services-mac:
	docker compose -f docker-compose.mac.yml up -d
docker:
	docker compose up --build -d
