import os
from unittest.mock import patch, MagicMock
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

def test_get_fractal_app_filenotfound():
    """
    """

    expected_error_message = 'Failed to find pyproject.toml in current directory.'

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.toml.loads", side_effect=FileNotFoundError):
        with pytest.raises(Exception) as e:
            controller._get_fractal_app()

    assert str(e.value) == expected_error_message


def test_get_fractal_app_keyerror():
    """
    """

    expected_error_message = 'Failed to find fractal key in pyproject.toml.'

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.toml.loads", new=MagicMock(return_value={})):
        with pytest.raises(Exception) as e:
            controller._get_fractal_app()

    assert str(e.value) == expected_error_message


def test_get_fractal_app_return_pyproject():
    """
    #? create a temp directory and create a pyproject.toml, then call function
    """