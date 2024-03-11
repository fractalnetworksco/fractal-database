import pytest
from fractal_database.controllers.fractal_database_controller import FractalDatabaseController
from unittest.mock import MagicMock, patch
from fractal.matrix.utils import parse_matrix_id, InvalidMatrixIdException

FILE_PATH = "fractal_database.controllers.fractal_database_controller"

def test_init_no_access_token_no_nomigrate():
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()


    controller.access_token = None
    with pytest.raises(SystemExit):
        controller.init()




