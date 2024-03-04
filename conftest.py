import asyncio
import os
import secrets
from typing import Generator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fractal.cli.controllers.auth import AuthController
from fractal_database.models import Database, Device  # MatrixCredentials
from nio import AsyncClient

# from homeserver.core.models import MatrixAccount

try:
    TEST_HOMESERVER_URL = os.environ["MATRIX_HOMESERVER_URL"]
    TEST_USER_USER_ID = os.environ["HS_USER_ID"]
    TEST_USER_ACCESS_TOKEN = os.environ["MATRIX_ACCESS_TOKEN"]
except KeyError as e:
    raise Exception(
        f"Please run prepare-test.py first, then source the generated environment file: {e}"
    )


@pytest.fixture
def test_homeserver_url() -> str:
    return os.environ.get("TEST_HOMESERVER_URL", "http://localhost:8008")


@pytest.fixture(scope="function")
def logged_in_db_auth_controller(test_homeserver_url):
    # create an AuthController object and login variables
    auth_cntrl = AuthController()
    matrix_id = "@admin:localhost"

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


# @pytest.fixture(scope="function")
# def test_matrix_creds(db, test_database):
#     """
#     """
#     unique_id = f"test-device-{secrets.token_hex(8)[:4]}"

#     return MatrixCredentials.objects.create(name=unique_id)


@pytest.fixture
def test_user_access_token():
    return os.environ["MATRIX_ACCESS_TOKEN"]


# @pytest.fixture(scope="function")
# def matrix_client() -> Generator[AsyncClient, None, None]:
#     client = AsyncClient(homeserver=TEST_HOMESERVER_URL)
#     client.user_id = TEST_USER_USER_ID
#     client.access_token = TEST_USER_ACCESS_TOKEN
#     yield client
#     asyncio.run(client.close())


# @pytest.fixture(scope="function")
# def test_user(db):
#     return MatrixAccount.objects.create(matrix_id=TEST_USER_USER_ID)


# @pytest.fixture(scope="function")
# def database(db):
#     return Database.objects.get()


# @pytest.fixture
# def test_room_id() -> str:
#     return TEST_ROOM_ID


# @pytest.fixture
# def test_user_id() -> str:
#     return TEST_USER_USER_ID
