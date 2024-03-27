import json
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
from fractal_database_matrix.models import MatrixReplicationTarget

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"
DEFAULT_FRACTAL_SRC_DIR = os.path.join(data_dir, "src")
pytestmark = pytest.mark.django_db(transaction=True)


class NotMatrixReplicationTarget:
    """ """


def test_fetch_no_databases(logged_in_db_auth_controller, _use_django):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.asyncio.run") as mock_run:
        with patch(
            "fractal_database.models.Database.objects.all", return_value=[]
        ) as mock_database_all:
            with patch(f"{FILE_PATH}.isinstance") as mock_isisntance:
                controller.fetch()

    mock_run.assert_not_called()
    mock_isisntance.assert_not_called()


def test_fetch_not_matrixreplicationtarget(logged_in_db_auth_controller, _use_django):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    mock_db = [MagicMock()]
    mock_db[0].primary_target.return_value = MagicMock(spec=NotMatrixReplicationTarget)

    with patch(
        "fractal_database.models.Database.objects.all", return_value=mock_db
    ) as mock_database_all:
        with patch(f"{FILE_PATH}.asyncio.run") as mock_run:
            controller.fetch()

    mock_run.assert_not_called()


def test_fetch_no_room_id(logged_in_db_auth_controller, _use_django, test_room_id):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    mock_db = [MagicMock()]
    mock_primary_target = MagicMock(spec=MatrixReplicationTarget)
    mock_primary_target.metadata.get = MagicMock(return_value=None)
    mock_db[0].primary_target.return_value = mock_primary_target

    with patch(
        "fractal_database.models.Database.objects.all", return_value=mock_db
    ) as mock_database_all:
        with patch(f"{FILE_PATH}.asyncio.run") as mock_run:
            controller.fetch()

    mock_run.assert_not_called()


def test_fetch_with_room_id(logged_in_db_auth_controller, _use_django, test_room_id):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    mock_db = [MagicMock()]
    mock_primary_target = MagicMock(spec=MatrixReplicationTarget)
    mock_primary_target.room_id = MagicMock(spec=test_room_id)
    mock_db[0].primary_target.return_value = mock_primary_target

    with patch(
        "fractal_database.models.Database.objects.all", return_value=mock_db
    ) as mock_database_all:
        with patch(f"{FILE_PATH}.asyncio.run") as mock_run:
            controller.fetch()

    mock_run.assert_called_once()
