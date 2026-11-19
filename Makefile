run:
	uvicorn app.main:app --app-dir gateway --reload --port 8000
test:
	pytest -q
lint:
	ruff check .