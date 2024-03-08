import pytest
from fractal_database.controllers.fractal_database_controller import FractalDatabaseController, RoomGetStateEventError
from unittest.mock import patch, MagicMock, AsyncMock


FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"

@pytest.mark.skip(reason='cant enter function')
async def test_sync_database_RoomGetStateEventError(test_room_id, _use_django):
    """
    """

    controller = FractalDatabaseController()

    with patch(f"{FRACTAL_PATH}.room_get_state_event") as mock_room_get_state:
        mock_room_get_state.return_value = MagicMock(spec=RoomGetStateEventError)
        # with pytest.raises(Exception):
        await controller._sync_database_metadata(controller, room_id=test_room_id)

        