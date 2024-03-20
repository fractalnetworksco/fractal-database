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
    TransferMonitor
)

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"
DEFAULT_FRACTAL_SRC_DIR = os.path.join(data_dir, "src")


def test_upload_filenotfound(logged_in_db_auth_controller):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.os.path.getsize", side_effect=FileNotFoundError) as mock_get_size:
        with pytest.raises(SystemExit):
            controller.upload('test_file')

def test_upload_verbose_cases(logged_in_db_auth_controller, temp_directory_with_pyproject):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    current_dir = os.getcwd()

    try:
        os.chdir(temp_directory_with_pyproject)
    except:
        raise

    with patch(f"{FILE_PATH}.TransferMonitor", return_value=MagicMock(spec=TransferMonitor)) as mock_monitor:
        with patch(f"{FILE_PATH}.partial", return_value=MagicMock()) as mock_progress_bar:
            with patch(f"{FILE_PATH}.asyncio.run", return_value=MagicMock()) as mock_asyncio:
                result = controller.upload('pyproject.toml', True)

    mock_monitor.assert_called_once()
    mock_progress_bar.assert_called_once()
    mock_asyncio.assert_called_once()
    assert isinstance(result, MagicMock)


    with patch(f"{FILE_PATH}.TransferMonitor", return_value=MagicMock(spec=TransferMonitor)) as mock_monitor:
        with patch(f"{FILE_PATH}.partial", return_value=MagicMock()) as mock_progress_bar:
            with patch(f"{FILE_PATH}.asyncio.run", return_value=MagicMock()) as mock_asyncio:
                result = controller.upload('pyproject.toml', False)

    mock_monitor.assert_not_called()
    mock_progress_bar.assert_not_called()
    mock_asyncio.assert_called_once()
    assert isinstance(result, MagicMock)

    os.chdir(current_dir)

def test_upload_fail_to_upload(logged_in_db_auth_controller, temp_directory_with_pyproject):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    current_dir = os.getcwd()

    try:
        os.chdir(temp_directory_with_pyproject)
    except:
        raise

    with patch(f"{FILE_PATH}.asyncio.run", side_effect=Exception) as mock_asyncio:
        with pytest.raises(SystemExit):
            result = controller.upload('pyproject.toml', False)

    os.chdir(current_dir)

def test_upload_keyboard_interrupt(logged_in_db_auth_controller, temp_directory_with_pyproject):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    current_dir = os.getcwd()

    try:
        os.chdir(temp_directory_with_pyproject)
    except:
        raise

    with patch(f"{FILE_PATH}.asyncio.run", side_effect=KeyboardInterrupt) as mock_asyncio:
        with pytest.raises(SystemExit):
            result = controller.upload('pyproject.toml', False)

    os.chdir(current_dir)

