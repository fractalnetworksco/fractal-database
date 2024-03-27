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
pytestmark = pytest.mark.django_db(transaction=True)

#! NOT FINISHED

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

    os.chdir(original_directory)


def test_build_fail_to_connect_to_docker(temp_directory_with_pyproject):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    # pyproject = {
    #     "tool": {
    #         "fractal": {
    #             "namespace": "test_project_name"
    #         }
    #     }
    # }

    controller._get_fractal_app = MagicMock()

    with patch(f"{FILE_PATH}.docker.from_env", side_effect=Exception) as mock_from_env:
        with pytest.raises(SystemExit):
            controller._build(name='test_project_name')


def test_build_fractal_base_image():
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    controller._get_fractal_app = MagicMock()

    mock_docker = MagicMock()
    mock_docker.images.list.return_value = []
    response = [
        {"stream": "This is a stream message 1\n"},
        {"stream": "This is a stream message 2\n"},
        {"other_key": "This is another key"},
        {"stream": "This is a stream message 3\n"},
    ]
    mock_docker.api.build = MagicMock(return_value=response)

    with patch(f"{FILE_PATH}.FractalDatabaseController.build_base") as mock_build_base:
        with patch(f"{FILE_PATH}.docker.from_env", return_value=mock_docker):
            controller._build(name='test_project_name', verbose=True)

    mock_build_base.assert_called_once()
    mock_docker.api.build.assert_called()


    





