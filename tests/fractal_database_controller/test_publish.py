import asyncio
import os
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import requests
from fractal.cli.utils import write_user_data
from fractal_database.controllers.fractal_database_controller import (
    FRACTAL_DATA_DIR,
    FractalDatabaseController,
    TransferMonitor,
    data_dir,
    init_poetry_project,
)

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"
DEFAULT_FRACTAL_SRC_DIR = os.path.join(data_dir, "src")
pytestmark = pytest.mark.django_db(transaction=True)


def test_publish_fail_to_load_project(logged_in_db_auth_controller, _use_django):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with pytest.raises(SystemExit):
        controller.publish("")


def test_publish_keyerror(
    logged_in_db_auth_controller, _use_django, temp_directory_with_pyproject
):
    """ 
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    original_dir = os.getcwd()

    try:
        os.chdir(temp_directory_with_pyproject)
    except:
        raise

    with patch(f"{FILE_PATH}.FractalDatabaseController._get_fractal_app", return_value={}):
        with pytest.raises(SystemExit):
            controller.publish(controller)

    os.chdir(original_dir)


def test_publish_fail_to_extract_image(
    logged_in_db_auth_controller, _use_django, temp_directory_with_pyproject
):

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    original_dir = os.getcwd()

    try:
        os.chdir(temp_directory_with_pyproject)
    except:
        raise


    with patch(f"{FILE_PATH}.FractalDatabaseController._build") as mock_build:
        with patch(f"{FILE_PATH}.subprocess.run", side_effect=Exception) as mock_subprocess_run:
            with pytest.raises(SystemExit):
                    controller.publish(controller)

    mock_subprocess_run.assert_called()

    os.chdir(original_dir)


def test_publish_app_published(
    logged_in_db_auth_controller, _use_django, temp_directory_with_pyproject
):

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()
    controller.upload = MagicMock()

    original_dir = os.getcwd()

    try:
        os.chdir(temp_directory_with_pyproject)
    except:
        raise


    with patch(f"{FILE_PATH}.FractalDatabaseController._build") as mock_build:
        with patch(f"{FILE_PATH}.subprocess.run") as mock_subprocess_run:
            with patch("fractal_database.models.AppCatalog.objects.create") as mock_app_catalog_create:
                controller.publish(controller)

    mock_subprocess_run.assert_called()
    mock_app_catalog_create.assert_called_once()

    os.chdir(original_dir)