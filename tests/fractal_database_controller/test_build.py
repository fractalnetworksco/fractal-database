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

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"
DEFAULT_FRACTAL_SRC_DIR = os.path.join(data_dir, "src")


def test_build_no_fractal_app(temp_directory):
    """
    #? name = f"{pyproject['tool']} line should never be reached in exception cases, consider
        #? no cover-ing that line
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    original_directory = os.getcwd()
    os.chdir(temp_directory)

    with pytest.raises(Exception):
        controller._get_fractal_app()

    with pytest.raises(SystemExit):
        controller._build(name="test_name")

    # keyerror case
    with patch(f"{FILE_PATH}.FractalDatabaseController._get_fractal_app") as mock_get_fractal_app:
        mock_get_fractal_app.return_value = {}
        with pytest.raises(SystemExit):
            controller._build(name="test_name")


def test_build_fail_to_connect_to_docker(temp_directory_with_pyproject):
    """
    #? pyproject exists and looks right, not passing the get_fractal_app function call
    """

    assert os.path.exists(os.path.join(temp_directory_with_pyproject, 'pyproject.toml'))
    with open(f"{temp_directory_with_pyproject}/pyproject.toml", 'r') as f:
        contents = f.read()
        print('here============', contents)

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.docker.from_env", side_effect=Exception) as mock_from_env:
        # with pytest.raises(SystemExit):
        controller._build(name='test_project_name')

