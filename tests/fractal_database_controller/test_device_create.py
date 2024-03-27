import json
import socket
import os
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fractal.cli.utils import write_user_data
from fractal_database.controllers.fractal_database_controller import (
    FRACTAL_DATA_DIR,
    FractalDatabaseController,
    data_dir,
    init_poetry_project,
)
from fractal_database.models import Device

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"
DEFAULT_FRACTAL_SRC_DIR = os.path.join(data_dir, "src")
pytestmark = pytest.mark.django_db(transaction=True)


def test_device_create_use_socket_name(_use_django, logged_in_db_auth_controller):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()
    expected_name = socket.gethostname()

    with patch(
        "fractal_database.models.Device.objects.create", return_value=MagicMock(spec=Device)
    ) as mock_create_device:
        controller.device_create()

    args = mock_create_device.call_args_list

    assert expected_name in str(args)


def test_device_create_use_given_name(_use_django, logged_in_db_auth_controller):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()
    expected_name = "test_name"
    socket_name = socket.gethostname()

    with patch(
        "fractal_database.models.Device.objects.create", return_value=MagicMock(spec=Device)
    ) as mock_create_device:
        controller.device_create(expected_name)

    args = mock_create_device.call_args_list

    assert expected_name in str(args)
    assert socket_name not in str(args)











