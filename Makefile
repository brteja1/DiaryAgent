PYTHON ?= python
PYTEST ?= pytest
.DEFAULT_GOAL := test

.PHONY: submodules deps test clean

submodules:
	git submodule update --init --recursive

deps: submodules
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTEST) -q

clean:
	find . -type d \( -name .git -o -name deps \) -prune -o -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
	find . -type d \( -name .git -o -name deps \) -prune -o -type f \( -name '*.pyc' -o -name '*.pyo' \) -exec rm -f {} +
