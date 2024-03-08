import pytest
from fractal_database.controllers.fractal_database_controller import FractalDatabaseController, RoomGetStateEventError
from unittest.mock import patch, MagicMock, AsyncMock

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"

async def test_sync_data_no_tasks(test_room_id):
    """
    """

    controller = FractalDatabaseController()

    with patch("fractal_database_matrix.broker.broker") as mock_broker:
        mock_broker.replication_queue.get_tasks = AsyncMock(return_value=[])
        await controller._sync_data(test_room_id)

    #! asserts


