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


def test_verify_repos_cloned_missing_project(temp_directory):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    original_dir = os.getcwd()

    try:
        os.chdir(temp_directory)
    except:
        raise

    projects_with_one_missing_project = [
        "fractal-database-matrix",
        "fractal-database",
        "taskiq-matrix",
        "fractal-matrix-client",
        "fractal-gateway-v2",
    ]

    for project in projects_with_one_missing_project:
        os.makedirs(project, exist_ok=True)

    assert controller._verify_repos_cloned(temp_directory)

    try:
        os.rmdir(projects_with_one_missing_project[0])
    except:
        raise

    assert not controller._verify_repos_cloned(os.path.dirname(os.getcwd()))

    os.chdir(original_dir)
