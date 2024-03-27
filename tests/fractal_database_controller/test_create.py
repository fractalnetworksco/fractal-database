import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fractal_database.controllers.fractal_database_controller import (
    FRACTAL_DATA_DIR,
    FractalDatabaseController,
)

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"
pytestmark = pytest.mark.django_db(transaction=True)


def test_create_FileFoundError(_use_django):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.os.mkdir", side_effect=FileExistsError) as mock_mkdir:
        with patch(f"{FILE_PATH}.os.getcwd") as mock_getcwd:
            with pytest.raises(SystemExit):
                controller.create("test_database")

    mock_getcwd.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_create_db_created(_use_django, temp_directory):
    """ """

    project = "mytestapp"

    original_dir = os.getcwd()

    os.chdir(temp_directory)
    path = os.path.join(f"{os.getcwd()}/{project}")

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()
    db = MagicMock()
    repl_target = MagicMock()

    db.schedule_replication = MagicMock()
    repl_target.matrixcredentials_set = MagicMock()
    repl_target.matrixcredentials_set.add = MagicMock()

    with patch(
        "fractal_database.models.Database.objects.create", return_value=db
    ) as mock_database_create:
        with patch(
            "fractal_database_matrix.models.MatrixReplicationTarget.objects.create",
            return_value=repl_target,
        ) as mock_repl_create:
            controller.create(project)

    repl_target.matrixcredentials_set.add.assert_called_once()
    db.schedule_replication.assert_called_once()
    mock_database_create.assert_called_with(name=project)

    os.chdir(original_dir)
