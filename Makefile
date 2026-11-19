run:
	uvicorn app.main:create_app --factory --app-dir gateway --reload --port 8000
test:
	pytest -q
lint:
	ruff check .