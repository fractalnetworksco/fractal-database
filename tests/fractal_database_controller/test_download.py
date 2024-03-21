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


def test_download_fail_to_load_app(logged_in_db_auth_controller):
    """ 
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    mxc = 'test_mxc' 

    with patch(f"{FILE_PATH}.FractalDatabaseController.download_file") as mock_download_file:
        with patch(f"{FILE_PATH}.subprocess.run", side_effect=Exception) as mock_subprocess_run:
            with patch(f"{FILE_PATH}.os.remove") as mock_os_remove:
                with pytest.raises(SystemExit):
                    controller.download(mxc)

    mock_download_file.assert_called_once()
    mock_subprocess_run.assert_called_once()
    mock_os_remove.assert_not_called()

def test_download_app_loaded_into_docker(logged_in_db_auth_controller):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    mxc = 'test_mxc' 

    with patch(f"{FILE_PATH}.FractalDatabaseController.download_file") as mock_download_file:
        with patch(f"{FILE_PATH}.subprocess.run") as mock_subprocess_run:
            with patch(f"{FILE_PATH}.os.remove") as mock_os_remove:
                controller.download(mxc)

    mock_download_file.assert_called_once()
    mock_subprocess_run.assert_called_once()
    mock_os_remove.assert_called_once()