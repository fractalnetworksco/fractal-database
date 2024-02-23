#!/bin/bash

# expected environment variables:
# ENV - environment name (e.g. test, dev, prod)
# TEST_CONFIG_DIR - path to the test-config directory

set -e

PREPARE_SCRIPT="$TEST_CONFIG_DIR/prepare-test.py"

python3 "$PREPARE_SCRIPT"

# environment file should be created by prepare-test.py
source "$TEST_CONFIG_DIR/fractal_database.$ENV.env"

cd /code

PYTHONPATH="$TEST_CONFIG_DIR/test_project" pytest -v -s --asyncio-mode=auto --cov=/code/fractal_database --cov-report=lcov --cov-report=term tests/
