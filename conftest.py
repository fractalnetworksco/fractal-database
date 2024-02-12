import asyncio
import os
from typing import Generator
from uuid import uuid4

import pytest
# from fractal_database.models import Database
from nio import AsyncClient

# from homeserver.core.models import MatrixAccount

try:
    TEST_HOMESERVER_URL = os.environ["MATRIX_HOMESERVER_URL"]
    TEST_USER_USER_ID = os.environ["HS_USER_ID"]
    TEST_USER_ACCESS_TOKEN = os.environ["MATRIX_ACCESS_TOKEN"]
    TEST_ROOM_ID = os.environ["MATRIX_ROOM_ID"]
except KeyError as e:
    raise Exception(
        f"Please run prepare-test.py first, then source the generated environment file: {e}"
    )


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
