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

BASE ?= http://localhost:8000
LABEL ?= kong

load:
	python bench/loadgen.py --base-url $(BASE) --key $(KEY) --label $(LABEL) --out bench/results/load-$(LABEL).json

METRICS ?= http://localhost:8001/metrics

drill:
	python bench/outage_drill.py --base-url $(BASE) --metrics-url $(METRICS) --key $(KEY) --out bench/results/drill.json

HARDWARE ?= not recorded

bench-embeddings:
	python bench/embeddings_eval.py --out bench/results/embeddings.json
report:
	python bench/make_report.py --hardware "$(HARDWARE)"
check-readme:
	@if grep -n "<<MEASURED" README.md; then echo "README still has unfilled placeholders"; exit 1; fi
