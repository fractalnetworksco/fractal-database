from unittest.mock import patch
from uuid import uuid4

import pytest
from fractal_database.controllers.fractal_database_controller import (
    FractalDatabaseController,
    FRACTAL_DATA_DIR,
)

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"


def test_verify_repos_cloned_all_repos_exist():
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    

