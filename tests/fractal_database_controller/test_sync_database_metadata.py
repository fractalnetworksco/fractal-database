from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fractal_database.controllers.fractal_database_controller import (
    FractalDatabaseController,
    RoomGetStateEventError,
)
from nio import RoomGetStateEventResponse

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"

pytestmark = pytest.mark.django_db(transaction=True)


async def test_sync_database_RoomGetStateEventError(test_room_id, _use_django):
    """
    Tests that an exception is raised if get_room_state_event returns a RoomGetStateEventError
    """

    controller = FractalDatabaseController()
    expected_message = str(uuid4())

    with patch(f"{FRACTAL_PATH}.room_get_state_event") as mock_room_get_state:
        mock_room_get_state.return_value = MagicMock(
            spec=RoomGetStateEventError, message=expected_message
        )
        with pytest.raises(Exception) as e:
            await controller._sync_database_metadata(room_id=test_room_id)

    assert str(e.value) == expected_message

async def test_sync_database_error_parsing_database(test_room_id, _use_django):
    """
    Tests that an exception is raised there is an error when trying to parse the database
    """

    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.json.loads", side_effect=Exception) as mock_json_loads:
        with patch(f"{FRACTAL_PATH}.room_get_state_event") as mock_room_get_state:
            response = MagicMock(spec=RoomGetStateEventResponse)
            mock_room_get_state.return_value = response
            with pytest.raises(Exception) as e:
                await controller._sync_database_metadata(room_id=test_room_id)

    assert 'Failed to parse database' in str(e.value)


@pytest.mark.skip(reason='json.loads return type error')
async def test_sync_database_RoomGetStateEventError_after_appending_fixture(new_matrix_room, _use_django, test_yaml_dict):
    """
    """

    mock_json_data = {"fixture": [{"pk": 123}]}
    controller = FractalDatabaseController()
    with patch(f"{FILE_PATH}.json.loads", return_value=mock_json_data) as mock_loads:
        with patch(f"{FRACTAL_PATH}.room_get_state_event") as mock_room_get_state:
            response = MagicMock(spec=RoomGetStateEventResponse)
            response.content = 'test_content'
            mock_room_get_state.return_value = response
            await controller._sync_database_metadata(room_id=new_matrix_room)