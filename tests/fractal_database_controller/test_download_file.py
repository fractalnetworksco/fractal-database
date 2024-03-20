import os
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
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


def test_download_file_fail_to_convert_to_http(logged_in_db_auth_controller):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.asyncio.run", return_value=None) as mock_asyncio:
        with pytest.raises(SystemExit):
            controller.download_file("test_mxr_uri")


def test_download_file_with_content_disposition(
    logged_in_db_auth_controller, temp_directory_with_pyproject
):
    """
    Figure out where its downloaded to, and assert that the name isnt app.tar.gz
    print statement on 863
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    original_dir = os.getcwd()

    try:
        os.chdir(temp_directory_with_pyproject)
    except:
        raise

    mxc = controller.upload("pyproject.toml")
    assert mxc is not None

    controller.download_file(mxc)
    contents = os.listdir(".")
    print("contents===============", contents)

    os.chdir(original_dir)
