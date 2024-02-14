import asyncio
import os
import secrets
from typing import Generator
from uuid import uuid4
from fractal_database.models import Device, Database

import pytest
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

@pytest.fixture(scope='function')
def test_database(db):
    """
    """

    from fractal_database.signals import create_database_and_matrix_replication_target
    create_database_and_matrix_replication_target()

    return Database.current_db()





@pytest.fixture(scope='function')
def test_device(db, test_database):
    """
    """
    unique_id = f"test-device-{secrets.token_hex(8)[:4]}"

    return Device.objects.create(name=unique_id)




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
