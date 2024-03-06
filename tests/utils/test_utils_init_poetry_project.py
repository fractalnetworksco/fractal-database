import io
import os
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

from fractal_database.signals import FRACTAL_EXPORT_DIR
from fractal_database.utils import init_poetry_project

FILE_PATH = "fractal_database.utils"


def test_init_poetry_project_in_memory():
    """
    Tests the case where in_memory is passed as True, causing the pyproject.toml to not be
    written.
    """

    # generate a project name
    project_name = secrets.token_hex(8)

    # patch the open function
    with patch(f"{FILE_PATH}.open") as mock_open:
        returned_pyproject_toml = init_poetry_project(project_name=project_name, in_memory=True)

    assert returned_pyproject_toml is not None

    # verify that open was never called
    mock_open.assert_not_called()


def test_init_poetry_project_create_pyproject():
    """
    Tests the case where in_memory is passed as False, causing the pyproject.toml file to
    be written.
    """

    # generate a project name
    project_name = secrets.token_hex(8)

    # create a working directory and cd into it
    test_dir = FRACTAL_EXPORT_DIR
    os.makedirs(f"{test_dir}/working_dir", exist_ok=True)
    os.chdir(f"{test_dir}/working_dir")

    try:
        # call the function
        returned_pyproject_toml = init_poetry_project(project_name=project_name, in_memory=False)

        # verify that the pyproject.toml file was created
        assert os.path.exists(f"{test_dir}/working_dir/pyproject.toml")
    except:
        # if it doesnt work, assert False
        assert False
    finally:

        # reset the working directory to its original location
        os.chdir(os.getcwd())
