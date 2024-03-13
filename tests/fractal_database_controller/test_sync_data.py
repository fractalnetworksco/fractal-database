from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fractal_database.controllers.fractal_database_controller import (
    FractalDatabaseController,
    RoomGetStateEventError,
    Receiver,
)
from taskiq_matrix.filters import create_room_message_filter
from taskiq_matrix.matrix_broker import MatrixBroker, AckableMessage

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


async def test_sync_data_with_tasks(test_matrix_broker, test_multiple_broker_message, test_room_id):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    test_broker: MatrixBroker = await test_matrix_broker()
    test_broker._init_queues = MagicMock()

    num_tasks = 5

    tasks = await test_multiple_broker_message(num_tasks)

    for task in tasks:
        await test_broker.kick(task)

    task_filter = create_room_message_filter(
        test_broker.room_id, types=[test_broker.replication_queue.task_types.task]
    )


    returned_tasks = await test_broker.replication_queue.get_tasks(timeout=0, task_filter=task_filter)

    for task in returned_tasks:
        task.data['args'] = ['test_args']

    test_broker.replication_queue.get_tasks = AsyncMock(side_effect=[returned_tasks, []])

    test_broker.replication_queue.yield_task = AsyncMock(spec=AckableMessage)

    with patch("fractal_database_matrix.broker.broker", test_broker):

        with patch(f"{FILE_PATH}.json.loads", return_value="test_args") as mock_loads:

            with patch(f"{FILE_PATH}.Receiver.callback") as mock_callback:

                await controller._sync_data(test_room_id)

    assert test_broker.replication_queue.get_tasks.call_count == 2

    assert mock_loads.call_count == num_tasks

    test_broker.replication_queue.yield_task.assert_called_once()