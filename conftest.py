import asyncio
import shutil
import os
import secrets
from typing import Generator
from unittest.mock import MagicMock, patch
from uuid import uuid4
from fractal_database.signals import FRACTAL_EXPORT_DIR

import pytest
from fractal.cli.controllers.auth import AuthController
from fractal_database.models import Database, Device, DummyReplicationTarget
from fractal_database.signals import clear_deferred_replications
from fractal_database_matrix.models import MatrixCredentials, MatrixReplicationTarget
from nio import AsyncClient

try:
    TEST_HOMESERVER_URL = os.environ["MATRIX_HOMESERVER_URL"]
    TEST_USER_USER_ID = os.environ["HS_USER_ID"]
    TEST_USER_ACCESS_TOKEN = os.environ["MATRIX_ACCESS_TOKEN"]
    TEST_ROOM_ID = os.environ['MATRIX_ROOM_ID']
except KeyError as e:
    raise Exception(
        f"Please run prepare-test.py first, then source the generated environment file: {e}"
    )

@pytest.fixture
def test_room_id():
    return TEST_ROOM_ID

@pytest.fixture
def test_homeserver_url() -> str:
    return os.environ.get("TEST_HOMESERVER_URL", "http://localhost:8008")


@pytest.fixture(scope="function")
def test_matrix_id() -> str:
    """ """
    return "@admin:localhost"


@pytest.fixture(scope="function")
def logged_in_db_auth_controller(test_homeserver_url, test_matrix_id):
    # create an AuthController object and login variables
    auth_cntrl = AuthController()
    matrix_id = test_matrix_id

    # log the user in patching prompt_matrix_password to use preset password
    with patch(
        "fractal.cli.controllers.auth.prompt_matrix_password", new_callable=MagicMock()
    ) as mock_password_prompt:
        mock_password_prompt.return_value = "admin"
        auth_cntrl.login(matrix_id=matrix_id, homeserver_url=test_homeserver_url)

    return auth_cntrl


@pytest.fixture(scope="function")
def test_database(db):
    """ """

    from fractal_database.signals import create_database_and_matrix_replication_target

    create_database_and_matrix_replication_target()

    return Database.current_db()


@pytest.fixture(scope="function")
def test_device(db, test_database):
    """ """
    unique_id = f"test-device-{secrets.token_hex(8)[:4]}"

    return Device.objects.create(name=unique_id)


@pytest.fixture(scope="function")
def second_test_device(db, test_database):
    """ """
    unique_id = f"test-device-{secrets.token_hex(8)[:4]}"

    return Device.objects.create(name=unique_id)


@pytest.fixture(scope="function")
def test_user_access_token():
    return os.environ["MATRIX_ACCESS_TOKEN"]


@pytest.fixture(scope="function")
def test_matrix_creds(test_device):
    """ """

    return test_device.matrixcredentials_set.get()

@pytest.fixture(autouse=True)
def cleanup():
    yield

    try:
        shutil.rmtree(FRACTAL_EXPORT_DIR)
    except FileNotFoundError:
        pass