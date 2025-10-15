
.PHONY: test cov fmt qa

test:
	pytest -q

cov:
	pytest --cov=app --cov-report=term-missing

fmt:
	ruff check app --fix

qa:
	ruff check app && bandit -r app -ll && pip-audit && pytest --cov=app --cov-report=xml
