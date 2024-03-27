"""
create deivce
create database
call function
assert the device is in the many
database.devices.get(device)
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fractal_database.controllers.fractal_database_controller import (
    FractalDatabaseController,
    RoomGetStateEventError,
)
from fractal_database.models import Database, DatabaseConfig
from fractal_database_matrix.models import MatrixReplicationTarget
from nio import RoomGetStateEventResponse

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"

pytestmark = pytest.mark.django_db(transaction=True)


def test_device_add(logged_in_db_auth_controller, test_database, test_device, _use_django):
    """ """

    controller = FractalDatabaseController()

    controller.device_add(
        test_device.name,
        test_database.name
    )

    assert test_database.devices.get(pk=test_device.pk)
