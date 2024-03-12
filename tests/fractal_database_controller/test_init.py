import secrets
from unittest.mock import MagicMock, patch

import pytest
from fractal.cli.utils import data_dir
from fractal.matrix.utils import InvalidMatrixIdException, parse_matrix_id
from fractal_database.controllers.fractal_database_controller import (
    FractalDatabaseController,
    write_user_data
)

FILE_PATH = "fractal_database.controllers.fractal_database_controller"


def test_init_no_access_token_no_nomigrate():
    """ 
    Tests that 
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    controller.access_token = None
    with pytest.raises(SystemExit):
        controller.init(no_migrate=False)


def test_init_module_not_found():
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(
        f"{FILE_PATH}.importlib.import_module", new=MagicMock(side_effect=ModuleNotFoundError)
    ) as mock_import_module:
        with pytest.raises(SystemExit):
            controller.init(app="test_app", no_migrate=True)

    mock_import_module.assert_called_once()


def test_init_no_project_name_cases():
    """ """

    expected_project_name = "fractaldb"
    expected_app_name = 'appdb'

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(
        f"{FILE_PATH}.os.path.exists", new=MagicMock(return_value=True)
    ) as mock_path_exists:
        controller.init(no_migrate=True, exist_ok=True)

    mock_path_exists.assert_called_with(f"{data_dir}/{expected_project_name}")

    with patch(
        f"{FILE_PATH}.os.path.exists", new=MagicMock(return_value=True)
    ) as mock_path_exists:
        with patch(
            f"{FILE_PATH}.importlib.import_module", new=MagicMock(return_value=True)
        ) as mock_import_module:
            controller.init(app="test_app_name", no_migrate=True, exist_ok=True)

    mock_path_exists.assert_called_with(f"{data_dir}/{expected_app_name}")

def test_init_not_exist_okay():
    """
    """
    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(
        f"{FILE_PATH}.os.path.exists", new=MagicMock(return_value=True)
    ) as mock_path_exists:
        with pytest.raises(SystemExit):
            controller.init(no_migrate=True, exist_ok=False)

    mock_path_exists.assert_called()


def test_init_error_creating_project():
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.os.path.join", side_effect=Exception) as mock_join:
        with pytest.raises(SystemExit):
            controller.init(no_migrate=True, exist_ok=False)

    mock_join.assert_called_once()

def test_init_no_yaml_project_found():
    """
    """

    projects_dict = {'fractaldb': {"name": 'fractaldb'}}

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    controller.migrate = MagicMock()
    controller.access_token = "test_access_token"

    with patch(f"{FILE_PATH}.write_user_data") as mock_write_user_data:
        with patch(f"{FILE_PATH}.read_user_data", side_effect=FileNotFoundError) as mock_read_user_data:
            controller.init(no_migrate=False, exist_ok=False)

    mock_write_user_data.assert_called_with(
        projects_dict,
        "projects.yaml"
    )

    controller.migrate.assert_called_once()

@pytest.mark.django_db(transaction=True)
def test_init_existing_yaml_file(test_yaml_dict, logged_in_db_auth_controller):
    """
    """
    
    write_user_data(test_yaml_dict, 'projects.yaml')
    test_yaml_dict['fractaldb'] = {"name": 'fractaldb'}

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()
    controller.access_token = logged_in_db_auth_controller.show('access_token')


    with patch(f"{FILE_PATH}.write_user_data") as mock_write_user_data:
        print('calling')
        controller.init(no_migrate=False, exist_ok=True)

    args = mock_write_user_data.call_args[0][0]
    assert 'fractaldb' in args

