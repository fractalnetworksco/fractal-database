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
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    original_dir = os.getcwd()

    try:
        os.chdir(temp_directory_with_pyproject)
    except:
        raise

    mxc = controller.upload("pyproject.toml")
    assert mxc is not None

    http = asyncio.run(controller._mxc_to_http(mxc))

    if http:
        res = requests.head(http, allow_redirects=True)
    else:
        assert False

    new_file_name = "new_project_name.txt"
    res.headers["Content-Disposition"] = f"filename={new_file_name}"

    assert not os.path.exists(os.path.join(temp_directory_with_pyproject, new_file_name))

    with patch(f"{FILE_PATH}.requests.head", return_value=res) as mock_requests_head:
        controller.download_file(mxc)

    assert os.path.exists(os.path.join(temp_directory_with_pyproject, new_file_name))
    os.chdir(original_dir)


def test_download_file_no_content_disposition(
    logged_in_db_auth_controller, temp_directory_with_pyproject
):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    original_dir = os.getcwd()

    try:
        os.chdir(temp_directory_with_pyproject)
    except:
        raise

    mxc = controller.upload("pyproject.toml")
    assert mxc is not None

    http = asyncio.run(controller._mxc_to_http(mxc))

    if http:
        res = requests.head(http, allow_redirects=True)
    else:
        assert False

    new_file_name = "app.tar.gz"
    del res.headers["Content-Disposition"]

    assert not os.path.exists(os.path.join(temp_directory_with_pyproject, new_file_name))

    with patch(f"{FILE_PATH}.requests.head", return_value=res) as mock_requests_head:
        controller.download_file(mxc, verbose=True)

    assert os.path.exists(os.path.join(temp_directory_with_pyproject, new_file_name))
    os.chdir(original_dir)


def test_download_file_fail_to_download(
    logged_in_db_auth_controller, temp_directory_with_pyproject
):

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    original_dir = os.getcwd()

    try:
        os.chdir(temp_directory_with_pyproject)
    except:
        raise

    mxc = controller.upload("pyproject.toml")
    assert mxc is not None

    http = asyncio.run(controller._mxc_to_http(mxc))

    if http:
        res = requests.head(http, allow_redirects=True)
    else:
        assert False

    new_file_name = "app.tar.gz"
    del res.headers["Content-Disposition"]

    assert not os.path.exists(os.path.join(temp_directory_with_pyproject, new_file_name))

    with patch(f"{FILE_PATH}.requests.head", return_value=res) as mock_requests_head:
        with patch(f"{FILE_PATH}.subprocess.run", side_effect=Exception) as mock_subprocess_run:
            with pytest.raises(SystemExit):
                controller.download_file(mxc, verbose=True)

    assert not os.path.exists(os.path.join(temp_directory_with_pyproject, new_file_name))
    os.chdir(original_dir)
