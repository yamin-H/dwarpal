run:
	uvicorn app.main:create_app --factory --app-dir gateway --reload --port 8000
test:
	pytest -q
lint:
	ruff check .
up:
	docker compose up -d --build
down:
	docker compose down
logs:
	docker compose logs -f gateway kong
e2e:
	DWARPAL_E2E_URL=http://localhost:8000 pytest tests/integration -q
check-stream:
	python scripts/check_streaming.py --key $(KEY)
	
bench:
	python bench/threshold_sweep.py