.PHONY: help setup data test pipeline figures verify clean-outputs

PY ?= python3

help:
	@echo "make setup     install the package in editable mode"
	@echo "make data      download every dataset (idempotent, cached, hashed)"
	@echo "make test      run the test suite (uses pytest if present, else the bundled runner)"
	@echo "make pipeline  run the analysis end to end from cached data"
	@echo "make figures   regenerate every figure"
	@echo "make verify    re-hash every downloaded file against data/raw/_manifest.json"
	@echo "make all       data -> test -> pipeline -> figures"

setup:
	$(PY) -m pip install -e .

data:
	$(PY) scripts/fetch_data.py

test:
	@if $(PY) -c "import pytest" 2>/dev/null; then \
		$(PY) -m pytest -q; \
	else \
		$(PY) scripts/run_tests.py; \
	fi

pipeline:
	$(PY) scripts/run_pipeline.py

figures:
	$(PY) scripts/run_pipeline.py --only figures

verify:
	@$(PY) -c "import sys; sys.path.insert(0,'src'); \
from svcarry.data.http import verify_manifest; \
p = verify_manifest(); \
print('manifest clean' if not p else p); \
sys.exit(1 if p else 0)"

clean-outputs:
	rm -rf reports/figures/*.png reports/figures/*.pdf reports/tables/*.csv \
	       data/interim/* data/processed/* reports/_pipeline_state.json
	@echo "removed derived outputs; data/raw and the manifest are untouched"

all: data test pipeline figures
