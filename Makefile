.PHONY: test-ci synapse

TEST = ""

test-ci:
	docker compose up synapse --build --force-recreate -d --wait
	docker compose up test --build --force-recreate --exit-code-from test
	docker compose down

setup:
	python test-config/prepare-test.py

test:
	export PYTHONPATH="test-config/test_project" && pytest -k ${TEST} -s --cov-config=.coveragerc --cov=fractal_database -v --asyncio-mode=auto --cov-report=lcov --cov-report=term tests/

qtest:
	export PYTHONPATH="test-config/test_project" && pytest -k ${TEST} -s --cov-config=.coveragerc --cov=fractal_database --asyncio-mode=auto --cov-report=lcov tests/

synapse:
	docker compose -f ./synapse/docker-compose.yml up synapse -d --force-recreate --build
