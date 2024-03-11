import pytest
from fractal_database.controllers.fractal_database_controller import FractalDatabaseController
from unittest.mock import MagicMock, patch
from fractal.matrix.utils import parse_matrix_id, InvalidMatrixIdException

FILE_PATH = "fractal_database.controllers.fractal_database_controller"

def test_list_invites_not_logged_in():
    """
    Tests that if the user is not logged in
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    # call the function to raise an exception
    with pytest.raises(SystemExit):
        controller.list_invites(controller)

def test_list_invites_no_pending_invites(logged_in_db_auth_controller):
    """
    Tests that the for loop is a no-op if there are no pending invites
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.isinstance") as mock_isinstance:
        controller.list_invites() 

    mock_isinstance.assert_not_called()


@pytest.mark.skip(reason='need two accounts and have one send an invite to the other')
def test_list_invites_pending_invites(logged_in_db_auth_controller, test_room_id):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    test_matrix_id = '@admin2:localhost'

    
    controller.invite(test_matrix_id, test_room_id, admin=True)

    controller.list_invites()