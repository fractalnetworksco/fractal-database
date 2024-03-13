from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fractal_database.controllers.fractal_database_controller import (
    FractalDatabaseController,
    RoomGetStateEventError,
)
from taskiq_matrix.filters import create_room_message_filter

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"


async def test_sync_data_no_tasks(test_room_id):
    """
    Tests that the loop breaks if there are no tasks in the broker's replication queue.
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    # patch the broker
    with patch("fractal_database_matrix.broker.broker") as mock_broker:
        # patch the json.loads function
        with patch(f"{FILE_PATH}.json.loads") as mock_json_loads:

            # set get_tasks to return an empty list
            mock_broker.replication_queue.get_tasks = AsyncMock(return_value=[])

            # call the function
            await controller._sync_data(test_room_id)

    # verify that get_tasks was only called once when the while loop is initially entered
    mock_broker.replication_queue.get_tasks.assert_called_once()

    # verify that the json.loads function call is never reached
    mock_json_loads.assert_not_called()


# @pytest.mark.skip(reason="figure out tasks, queues, and brokers. go back to taqskiq and test")
async def test_sync_data_with_tasks(test_matrix_broker, test_multiple_broker_message):
    """ """

    test_broker = await test_matrix_broker()
    test_broker.init_queues = MagicMock()

    tasks = await test_multiple_broker_message(5)

    for task in tasks:
        await test_broker.kick(task)

    task_filter = create_room_message_filter(
        test_broker.room_id, types=[test_broker.replication_queue.task_types.task]
    )

    returned_tasks = await test_broker.replication_queue.get_tasks(timeout=0, task_filter=task_filter)

    print("right here============", returned_tasks[0])

    # with patch("fractal_database_matrix.broker.broker", test_broker):
