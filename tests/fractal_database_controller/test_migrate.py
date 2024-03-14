from unittest.mock import patch
import os

import pytest
from fractal_database.controllers.fractal_database_controller import (
    FractalDatabaseController,
    FRACTAL_DATA_DIR,
)

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"

def test_migrate_not_logged_in():
    """
    Tests that a SystemExit error is raised if the user is not logged in
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with pytest.raises(SystemExit):
        controller.migrate('test_project_name')

def test_migrate_project_exists(logged_in_db_auth_controller):
    """
    """

    os.makedirs(f"{FRACTAL_DATA_DIR}/test_project", exist_ok=True)


    # create a FractalDatabaseController object
    controller = FractalDatabaseController()


    
    with patch(f"{FILE_PATH}.call_command") as mock_call_command:
        assert os.path.exists(os.path.join(FRACTAL_DATA_DIR, 'test_project'))
        controller.migrate('test_project')

    args = mock_call_command.call_args_list

    assert 'makemigrations' in str(args[0])
    assert 'migrate' in str(args[1])
    

def test_migrate_project_doesnt_exist(logged_in_db_auth_controller):
    """
    """

    assert not os.path.exists(os.path.join(FRACTAL_DATA_DIR, 'test_project'))

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.call_command") as mock_call_command:
        with pytest.raises(FileNotFoundError):
            controller.migrate('test_project')

    mock_call_command.assert_not_called()
    

