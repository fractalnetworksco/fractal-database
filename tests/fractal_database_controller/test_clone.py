import os
from unittest.mock import patch
from uuid import uuid4

import pytest
from fractal.cli.utils import write_user_data
from fractal_database.controllers.fractal_database_controller import (
    FRACTAL_DATA_DIR,
    FractalDatabaseController,
    data_dir
)

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"
DEFAULT_FRACTAL_SRC_DIR = os.path.join(data_dir, "src")
pytestmark = pytest.mark.django_db(transaction=True)


def test_clone_environ_source_dir_used():
    """
    """
    write_user_data({}, "test")

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    assert DEFAULT_FRACTAL_SRC_DIR == os.environ.get("FRACTAL_SOURCE_DIR", str(DEFAULT_FRACTAL_SRC_DIR))
    assert not os.path.exists(DEFAULT_FRACTAL_SRC_DIR)

    result = controller.clone()

    assert os.path.exists(DEFAULT_FRACTAL_SRC_DIR)

    assert result == None


def test_clone_environ_source_not_used(temp_directory):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch.dict(os.environ, {'FRACTAL_SOURCE_DIR': temp_directory}):
        controller.clone()

    assert len(os.listdir(temp_directory)) == 6


def test_clone_fail_to_clone():
    """
    """

    write_user_data({}, "test")

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.subprocess.run", side_effect=Exception) as mock_run:
        result = controller.clone()

    assert not result

        

    