import os
from unittest.mock import patch
from uuid import uuid4

import pytest
from fractal_database.controllers.fractal_database_controller import (
    FRACTAL_DATA_DIR,
    FractalDatabaseController,
)

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"


def test_verify_repos_cloned_all_repos_exist():
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    # gets the parent directory of the current working directory
    assert controller._verify_repos_cloned(os.path.dirname(os.getcwd()))


def test_verify_repos_cloned_wrong_directory_given():
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()
    path = "./repo_test"

    os.mkdir(path)

    assert os.path.exists(path)

    assert not controller._verify_repos_cloned()

    if os.path.exists(path):
        print("Deleting directory")
        os.rmdir(path)
    else:
        assert False


def test_verify_repos_cloned_nonexistant_project():
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    projects_with_one_nonexistant_project = [
        "fractal-database-matrix",
        "fractal-database",
        "taskiq-matrix",
        "fractal-matrix-client",
        "fractal-gateway-v2",
        "test-project-that-doesnt-exist", # insert a project that doesnt exist
    ]

    with patch(
        f"{FILE_PATH}.FractalDatabaseController._verify_repos_cloned.projects",
        new=projects_with_one_nonexistant_project,
    ):
        assert not controller._verify_repos_cloned(os.path.dirname(os.getcwd()))

    
