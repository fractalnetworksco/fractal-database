import pytest

from fractal_database.controllers.fractal_database_controller import FractalDatabaseController
from unittest.mock import MagicMock, patch
from fractal.matrix.utils import parse_matrix_id, InvalidMatrixIdException

FILE_PATH = "fractal_database.controllers.fractal_database_controller"

def test_invite_not_admin(logged_in_db_auth_controller):
    """
    Tests that an exception is raised if admin is passed as False to the function
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    # call the function to raise an exception
    with pytest.raises(Exception):
        controller.invite('test_user', 'test_room_id', admin=False)


def test_invite_not_logged_in():
    """
    Tests that a SystemExit is raised if the user is not logged in when invite is called.
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    # call the function to raise an exception
    with pytest.raises(SystemExit):
        controller.invite('test_user', 'test_room_id', admin=True)

def test_invite_invalid_matrix_id(logged_in_db_auth_controller):
    """
    Tests that an exception is raised if an invalid Matrix id is passed to the function
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()
    test_matrix_id = 'invalid_matrix_id'

    # verify that the matrix id is invalid
    with pytest.raises(InvalidMatrixIdException):
        parse_matrix_id(test_matrix_id)

    # call the function to raise an exception
    with pytest.raises(InvalidMatrixIdException):
        controller.invite(test_matrix_id, 'test_room_id', admin=True)


def test_invite_invite_sent(logged_in_db_auth_controller):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    test_matrix_id = '@admin:localhost'

    parse_matrix_id(test_matrix_id)

    with patch(f"{FILE_PATH}.FractalDatabaseController._invite_user") as mock_invite:
        controller.invite(test_matrix_id, 'test_room_id', admin=True)

    mock_invite.assert_called_once()
