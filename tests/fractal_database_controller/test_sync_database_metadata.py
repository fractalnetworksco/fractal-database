import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fractal_database.controllers.fractal_database_controller import (
    FractalDatabaseController,
    RoomGetStateEventError,
)
from fractal_database.models import DatabaseConfig
from fractal_database_matrix.models import MatrixReplicationTarget
from nio import RoomGetStateEventResponse

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"

pytestmark = pytest.mark.django_db(transaction=True)

json_fixture = """[
    {
        "model": "fractal_database.database",
        "pk": "9fe5821e-6475-43e6-8880-95fed05cecd1",
        "fields": {
        "date_created": "2024-03-14T14:10:42.121Z",
        "date_modified": "2024-03-14T14:10:42.121Z",
        "deleted": false,
        "object_version": 1,
        "name": "Fractal HomeServer",
        "description": null,
        "is_root": false,
        "devices": []
        }
    }
]"""


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

    assert "Failed to parse database" in str(e.value)
    mock_room_get_state.assert_called_once()


async def test_sync_database_RoomGetStateEventError_after_appending_fixture(
    new_matrix_room, _use_django
):
    """ """

    controller = FractalDatabaseController()

    test_json_fixture = json_fixture

    with patch(f"{FRACTAL_PATH}.room_get_state_event") as mock_room_get_state:
        response = MagicMock(spec=RoomGetStateEventResponse)
        response.content = {"fixture": test_json_fixture}
        mock_room_get_state.side_effect = [
            response,
            MagicMock(spec=RoomGetStateEventError, message="test_message"),
        ]
        with pytest.raises(Exception) as e:
            await controller._sync_database_metadata(room_id=new_matrix_room)

    assert str(e.value) == "test_message"


async def test_sync_database_error_parsing_second_fixture(new_matrix_room, _use_django):
    """ """

    controller = FractalDatabaseController()

    test_json_fixture = json_fixture

    with patch(f"{FRACTAL_PATH}.room_get_state_event") as mock_room_get_state:
        response = MagicMock(spec=RoomGetStateEventResponse)
        response2 = MagicMock(spec=RoomGetStateEventResponse)
        response.content = {"fixture": test_json_fixture}
        response2.content = {"test_fixture": test_json_fixture}
        mock_room_get_state.side_effect = [response, response2]
        with pytest.raises(Exception) as e:
            await controller._sync_database_metadata(room_id=new_matrix_room)

    assert "Failed to parse target fixture" in str(e.value)
    assert mock_room_get_state.call_count == 2


async def test_sync_database_fail_to_load_fixture(new_matrix_room, _use_django):
    """ """

    controller = FractalDatabaseController()

    test_json_fixture = json_fixture

    with patch(f"{FRACTAL_PATH}.room_get_state_event") as mock_room_get_state:
        response = MagicMock(spec=RoomGetStateEventResponse)
        response.content = {"fixture": test_json_fixture}
        mock_room_get_state.return_value = response
        with patch(
            "fractal_database.replication.tasks.replicate_fixture",
            new=AsyncMock(side_effect=Exception),
        ) as mock_replicate_fixture:
            with pytest.raises(Exception) as e:
                await controller._sync_database_metadata(room_id=new_matrix_room)

    assert "Failed to load fixture" in str(e.value)


async def test_sync_database_current_db_same_as_sync_db(new_matrix_room, _use_django):
    """ """

    controller = FractalDatabaseController()

    test_json_fixture = json_fixture

    with patch(f"{FRACTAL_PATH}.room_get_state_event") as mock_room_get_state:
        response = MagicMock(spec=RoomGetStateEventResponse)
        response.content = {"fixture": test_json_fixture}
        mock_room_get_state.return_value = response
        with patch(
            "fractal_database.replication.tasks.replicate_fixture", new=AsyncMock()
        ) as mock_replicate_fixture:
            db = MagicMock()
            with patch(
                "fractal_database.models.Database.acurrent_db", new=AsyncMock(return_value=db)
            ):
                db.aprimary_target = AsyncMock()
                db.pk = "9fe5821e-6475-43e6-8880-95fed05cecd1"
                result = await controller._sync_database_metadata(room_id=new_matrix_room)

    assert result is None
    db.aprimary_target.assert_not_called()


async def test_sync_database_current_db_doesnotexist(
    new_matrix_room, _use_django, test_yaml_dict, logged_in_db_auth_controller
):
    """
    #? having issues with os.environ variables in the function
    """

    controller = FractalDatabaseController()

    test_json_fixture = json_fixture

    with patch(f"{FRACTAL_PATH}.room_get_state_event") as mock_room_get_state:
        response = MagicMock(spec=RoomGetStateEventResponse)
        response.content = {"fixture": test_json_fixture}
        mock_room_get_state.return_value = response
        with patch(
            "fractal_database.replication.tasks.replicate_fixture", new=AsyncMock()
        ) as mock_replicate_fixture:
            with patch(
                "fractal_database.models.Database.acurrent_db",
                side_effect=DatabaseConfig.DoesNotExist,
            ):
                with patch(f"{FILE_PATH}.transaction.atomic") as mock_transaction_atomic:
                    with patch(
                        "fractal_database.models.DatabaseConfig.objects.create"
                    ) as mock_databaseconfig_create:
                        with patch(
                            "fractal_database.models.Device.objects.create"
                        ) as mock_device_create:
                            with patch(
                                "fractal_database.models.Database.objects.get"
                            ) as mock_database_get:
                                with patch(
                                    f"fractal_database_matrix.models.MatrixCredentials.objects.create"
                                ) as mock_creds_create:
                                    with patch.dict(
                                        os.environ,
                                        {"FRACTAL_DEVICE_NAME": "test name"},
                                        clear=True,
                                    ) as mock_os_environ:
                                        mock_os_environ["FRACTAL_PROJECT_NAME"] = test_yaml_dict[
                                            "test_project"
                                        ]
                                        mock_os_environ["MATRIX_ACCESS_TOKEN"] = (
                                            logged_in_db_auth_controller.show("access_token")
                                        )
                                        mock_os_environ["MATRIX_USER_ID"] = (
                                            logged_in_db_auth_controller.show("matrix_id")
                                        )
                                        result = await controller._sync_database_metadata(
                                            room_id=new_matrix_room
                                        )

    mock_transaction_atomic.assert_called()
    mock_creds_create.assert_called_once()


async def test_sync_database_fail_to_find_primary_target(new_matrix_room, _use_django):
    """ """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    test_json_fixture = json_fixture

    with patch(f"{FRACTAL_PATH}.room_get_state_event") as mock_room_get_state:
        response = MagicMock(spec=RoomGetStateEventResponse)
        response.content = {"fixture": test_json_fixture}
        mock_room_get_state.return_value = response
        with patch(
            "fractal_database.replication.tasks.replicate_fixture", new=AsyncMock()
        ) as mock_replicate_fixture:
            db = MagicMock()
            with patch(
                "fractal_database.models.Database.acurrent_db", new=AsyncMock(return_value=db)
            ):
                db.aprimary_target = AsyncMock(return_value=None)
                db.pk = "9fe5821e-6475-43e6-8880-95fed05cecd2"
                with pytest.raises(Exception) as e:
                    result = await controller._sync_database_metadata(room_id=new_matrix_room)

    assert "Failed to find primary target" in str(e.value)


@pytest.mark.skip(reason='error when mocking the matrix repl target select_related function')
async def test_sync_database_successful_sync(new_matrix_room, _use_django):
    """ 
    #? error when mocking the matrix repl target select_related function
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    test_json_fixture = json_fixture

    with patch(f"{FRACTAL_PATH}.room_get_state_event") as mock_room_get_state:
        response = MagicMock(spec=RoomGetStateEventResponse)
        response.content = {"fixture": test_json_fixture}
        mock_room_get_state.return_value = response
        with patch(
            "fractal_database.replication.tasks.replicate_fixture", new=AsyncMock()
        ) as mock_replicate_fixture:
            db = MagicMock()
            with patch(
                "fractal_database.models.Database.acurrent_db", new=AsyncMock(return_value=db)
            ):
                db.aprimary_target = AsyncMock()
                db.pk = "9fe5821e-6475-43e6-8880-95fed05cecd2"
                mock_query_object = MagicMock()
                mock_query_object.aget = AsyncMock()
                with patch(
                    "fractal_database_matrix.models.MatrixReplicationTarget.objects.select_related",
                    new=AsyncMock(return_value=mock_query_object),
                ) as mock_select_related:
                    with patch(f"{FILE_PATH}.sync_to_async") as mock_sync:
                        result = await controller._sync_database_metadata(room_id=new_matrix_room)

    mock_select_related.assert_called_once()
    mock_sync.assert_called_once()
