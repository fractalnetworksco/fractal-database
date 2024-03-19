import asyncio
import tempfile
import json
import os
import secrets
import shutil
from typing import Awaitable, Callable, Generator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fractal.matrix.async_client import FractalAsyncClient
from nio import RoomCreateError, RoomGetStateEventResponse, UnknownEvent
from fractal.cli.controllers.auth import AuthController
from fractal.cli.utils import data_dir, write_user_data
from fractal_database.models import Database, Device  # MatrixCredentials
from fractal_database.signals import FRACTAL_EXPORT_DIR
from taskiq.message import BrokerMessage
from taskiq_matrix.matrix_broker import MatrixBroker
from fractal_database.utils import init_poetry_project

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


@pytest.fixture(scope="function")
def _use_django(test_database, test_yaml_dict):
    """ """

    # create the projects.yaml file
    write_user_data(test_yaml_dict, "projects.yaml")

    # verify that the file exists in the data directory
    assert os.path.exists(os.path.join(data_dir, "projects.yaml"))

    os.environ["FRACTAL_PROJECT_NAME"] = test_yaml_dict["test_project"]

@pytest.fixture(scope="function")
def matrix_client() -> Generator[FractalAsyncClient, None, None]:
    client = FractalAsyncClient(access_token=TEST_USER_ACCESS_TOKEN)
    yield client
    asyncio.run(client.close())

@pytest.fixture(scope="function")
def new_matrix_room(matrix_client: FractalAsyncClient):
    """
    Creates a new room and returns its room id.
    """

    async def create():
        res = await matrix_client.room_create(name="test_room")
        if isinstance(res, RoomCreateError):
            await matrix_client.close()
            raise Exception("Failed to create test room")
        await matrix_client.close()
        return res.room_id

    return create


@pytest.fixture(scope="function")
def test_matrix_broker(new_matrix_room: Callable[[], Awaitable[str]]):
    async def create():
        """
        Creates a MatrixBroker instance whose queues are configured to
        use a new room each time the fixture is called.
        """
        client = FractalAsyncClient()
        new_room_id = await new_matrix_room()
        # os.environ['MATRIX_ROOM_ID'] = room_id

        broker = MatrixBroker()

        # set the broker's room id
        # broker.room_id = room_id
        broker.with_matrix_config(
            new_room_id, os.environ["MATRIX_HOMESERVER_URL"], os.environ["MATRIX_ACCESS_TOKEN"]
        )

        # use room_id for the queues
        broker._init_queues()

        return broker

    return create


@pytest.fixture
def test_multiple_broker_message():
    """
    Create a BrokerMessage Fixture
    """

    async def create(num_messages: int):
        messages = []
        for i in range(num_messages):
            task_id = str(uuid4())
            message = {
                "task_id": task_id,
                "foo": "bar",
            }

            # convert the message into json
            message_string = json.dumps(message)

            # encode the message into message bytes
            message_bytes = message_string.encode("utf-8")

            messages.append(
                BrokerMessage(
                    task_id=task_id, task_name="test_name", message=message_bytes, labels={'queue': "replication"}
                )
            )

        # create the BrokerMessage object
        return messages

    return create


@pytest.fixture
def temp_directory():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir

@pytest.fixture
def temp_directory_with_pyproject(temp_directory):
    current_dir = os.getcwd()

    try:
        os.chdir(temp_directory)
        init_poetry_project('test_project_name')
        os.chdir(current_dir)
    finally:
        yield temp_directory