import asyncio
import os
import secrets
import shutil
from typing import Generator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.core.management import call_command
from fractal.cli.controllers.auth import AuthController
from fractal.cli.utils import data_dir
from fractal_database.models import Database, Device  # MatrixCredentials
from fractal_database.signals import FRACTAL_EXPORT_DIR
from nio import AsyncClient

try:
    TEST_HOMESERVER_URL = os.environ["MATRIX_HOMESERVER_URL"]
    TEST_USER_USER_ID = os.environ["HS_USER_ID"]
    TEST_USER_ACCESS_TOKEN = os.environ["MATRIX_ACCESS_TOKEN"]
    TEST_ROOM_ID = os.environ["MATRIX_ROOM_ID"]
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
def test_database(db, logged_in_db_auth_controller):
    """ """

    from fractal_database.signals import create_database_and_matrix_replication_target

    create_database_and_matrix_replication_target()

    return Database.current_db()


@pytest.fixture()
def reset_database():
    def flush():
        call_command("flush", interactive=False, reset_sequences=True)

    return flush


@pytest.fixture()
def instance_database_room(test_database, reset_database) -> str:
    target = test_database.primary_target()
    room_id = target.metadata["room_id"]

    # clear the database so that we can load data from the above room_id
    reset_database()

    return room_id


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

    try:
        shutil.rmtree(data_dir)
    except FileNotFoundError:
        pass


@pytest.fixture(scope="function")
def test_yaml_dict():
    yaml_info = {
        "test_project": "test_project",
        "TEST_DATABASE": str(uuid4()),
        "ANOTHER_DATABASE": str(uuid4()),
        "YET_ANOTHER_DATABASE": str(uuid4()),
    }

    return yaml_info
