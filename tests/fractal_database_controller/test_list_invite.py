from unittest.mock import MagicMock, patch

import pytest
from fractal.matrix.utils import InvalidMatrixIdException, parse_matrix_id
from fractal_database.controllers.fractal_database_controller import (
    FractalDatabaseController,
)
from nio import InviteInfo, InviteMemberEvent, InviteNameEvent

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
pytestmark = pytest.mark.django_db(transaction=True)


#! ===============================
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


#! =============================== not sure if this test is needed, no assertions to make
def test_list_invites_pending_invites(logged_in_db_auth_controller, test_room_id):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()
    room_1_member_event = MagicMock(spec=InviteMemberEvent)
    room_1_member_event.membership = 'invite'
    room_1_member_event.name = "name 1"
    room_1_member_event.sender = "sender 1"
    room_1_member_event.room_id = "room id 1"

    room_2_member_event = MagicMock(spec=InviteMemberEvent)
    room_2_member_event.membership = 'invite'
    room_2_member_event.name = "name 2"
    room_2_member_event.sender = "sender 2"
    room_2_member_event.room_id = "room id 2"

    invites = {
        "room_id_1": InviteInfo(
            invite_state=[
                InviteNameEvent(source={}, sender="person 1", name="Room 1"),
                room_1_member_event,
                room_2_member_event,
            ]
        )
    }

    # Initialize a counter attribute to keep track of calls

    with patch(f"{FILE_PATH}.FractalDatabaseController._list_invites", return_value=invites):
        controller.list_invites()

