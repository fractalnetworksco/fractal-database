import os
from unittest.mock import patch
from uuid import uuid4

import pytest
from fractal.cli.utils import write_user_data
from fractal_database.controllers.fractal_database_controller import (
    FRACTAL_DATA_DIR,
    FractalDatabaseController,
    data_dir
)

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"
DEFAULT_FRACTAL_SRC_DIR = os.path.join(data_dir, "src")


def test_build_base_repos_not_cloned(temp_directory):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch.dict(os.environ, {'FRACTAL_SOURCE_DIR': temp_directory}):
        controller.clone()
        assert controller._verify_repos_cloned(temp_directory)

        with patch(f"{FILE_PATH}.FractalDatabaseController.clone") as mock_clone:
            controller.build_base()

    mock_clone.assert_not_called()

def test_build_base_failure_to_connect_to_docker(temp_directory):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()
    with patch.dict(os.environ, {'FRACTAL_SOURCE_DIR': temp_directory}):
        controller.clone()
        assert controller._verify_repos_cloned(temp_directory)

        with patch(f"{FILE_PATH}.FractalDatabaseController.clone") as mock_clone:
            with patch(f"{FILE_PATH}.docker.from_env", side_effect=Exception) as mock_from_env:
                with pytest.raises(SystemExit):
                    controller.build_base()

@pytest.mark.skip(reason='its working, just need to figure out how to assert')
def test_build_base_stream_verbose(temp_directory):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()
    with patch.dict(os.environ, {'FRACTAL_SOURCE_DIR': temp_directory}):
        controller.clone()
        assert controller._verify_repos_cloned(temp_directory)

        # response = controller.build_base(verbose=True)
        controller.build_base(verbose=True)

    # print('response====================================', response)
    # for line in response:
    #     print('line===', line)
    #     assert False
    




