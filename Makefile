PYTHON ?= python
PYTEST ?= pytest

.PHONY: test clean

test:
	$(PYTEST) -q

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
	find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
