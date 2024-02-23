.PHONY: test-ci synapse
SHELL=/bin/bash

TEST = ""

test-ci:
	docker compose up synapse --build --force-recreate -d --wait
	docker compose up test --build --force-recreate --exit-code-from test
	docker compose down

setup:
	python test-config/prepare-test.py

test:
	. fractal_database.dev.env && export PYTHONPATH="test-config/test_project" && pytest -k ${TEST} -s --cov-config=.coveragerc --cov=fractal_database -v --asyncio-mode=auto --cov-report=lcov --cov-report=term tests/

qtest:
	. fractal_database.dev.env && export PYTHONPATH="test-config/test_project" && pytest -k ${TEST} -s --cov-config=.coveragerc --cov=fractal_database --asyncio-mode=auto --cov-report=lcov tests/

synapse:
	docker compose -f ./synapse/docker-compose.yml up synapse -d --force-recreate --build
