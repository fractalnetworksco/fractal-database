from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from fractal_database.management.commands import replicate
from fractal_database.management.commands.replicate import (
    BaseCommand,
    Command,
    CommandError,
    Database,
    MatrixCredentials,
    MatrixReplicationTarget,
    ObjectDoesNotExist,
    RoomGetStateEventError,
)


@pytest.mark.asyncio
async def test_replicate_init_instance_database_already_configured():
    access_token = "sample_token"
    homeserver_url = "https://homeserver.com"
    room_id = "room_id"
    mock_acurrent_db = MagicMock()
    mock_acurrent_db.return_value = "mocked_database"
    with patch(
        "fractal_database.management.commands.replicate.Database.acurrent_db",
        return_value=mock_acurrent_db,
    ) as mock_acurrent_db:
        command_instance = replicate.Command()
        await replicate.Command._init_instance_db(
            self=command_instance,
            access_token=access_token,
            homeserver_url=homeserver_url,
            room_id=room_id,
        )
        mock_acurrent_db.assert_called_once()


@pytest.mark.asyncio
async def test_replicate_init_instance_db_objectdoesnotexit_pass():
    access_token = "sample_token"
    homeserver_url = "https://homeserver.com"
    room_id = "room_id"

    # Mock every function necessary (pretty sure there are some unnecessary mocks need to remove)
    with patch(
        "fractal_database.management.commands.replicate.Database.acurrent_db",
        side_effect=ObjectDoesNotExist,
    ) as mock_acurrent_db:
        with patch(
            "fractal_database.management.commands.replicate.MatrixClient"
        ) as mock_matrixclient:
            with patch("fractal_database.management.commands.replicate.json.loads") as mock_loads:
                with patch(
                    "fractal_database.replication.tasks.replicate_fixture", new=AsyncMock()
                ) as mock_replicate_fixture:
                    with patch(
                        "fractal_database.management.commands.replicate.Database.objects.aget",
                        new=AsyncMock(),
                    ) as mock_aget:
                        with patch(
                            "fractal_database.models.Database.aprimary_target", new=AsyncMock()
                        ) as mock_aprimary_target:
                            with patch(
                                "fractal_database.management.commands.replicate.DatabaseConfig.objects.acreate",
                                new=AsyncMock(),
                            ):
                                with patch(
                                    "fractal_database.management.commands.replicate.Device.objects.get_or_create"
                                ) as mock_get_or_create:
                                    with patch(
                                        "fractal_database.management.commands.replicate.MatrixCredentials.objects.get_or_create"
                                    ) as mock_matrixcredentials_get_or_create:
                                        # Mock the return value of get_or_create to return a tuple
                                        mock_device = MagicMock()
                                        mock_get_or_create.return_value = (mock_device, True)
                                        command_instance = replicate.Command()
                                        await replicate.Command._init_instance_db(
                                            self=command_instance,
                                            access_token=access_token,
                                            homeserver_url=homeserver_url,
                                            room_id=room_id,
                                        )
                                        mock_matrixcredentials_get_or_create.assert_called_once()


@pytest.mark.asyncio
async def test_replicate_init_instance_db_roomgetstateeventerror_raises_commanderror():
    access_token = "sample_token"
    homeserver_url = "https://homeserver.com"
    room_id = "room_id"
    with patch(
        "fractal_database.management.commands.replicate.Database.acurrent_db",
        side_effect=ObjectDoesNotExist,
    ) as mock_acurrent:
        mock_client_instance = AsyncMock()
        mock_client_instance.room_get_state_event = AsyncMock(side_effect=RoomGetStateEventError)
        with patch(
            "fractal_database.management.commands.replicate.MatrixClient"
        ) as mock_matrix_client:
            mock_matrix_client.return_value.__aenter__.return_value = mock_client_instance
            command_instance = Command()
            with pytest.raises(CommandError) as e:
                await command_instance._init_instance_db(access_token, homeserver_url, room_id)
            assert str(e.value) == "Failed to get database configuration from room state: room_id"
            mock_acurrent.assert_called_once
            mock_client_instance.room_get_state_event.assert_called_once_with(
                room_id, "f.database"
            )


@pytest.mark.asyncio
async def test_replicate_init_instance_db_targetstate_roomgetstateeventerror_raises_commanderror():
    access_token = "sample_token"
    homeserver_url = "https://homeserver.com"
    room_id = "room_id"
    with patch(
        "fractal_database.management.commands.replicate.Database.acurrent_db",
        side_effect=ObjectDoesNotExist,
    ) as mock_acurrent:
        mock_client_instance = AsyncMock()
        mock_client_instance.room_get_state_event = AsyncMock()
        # Define side_effect to raise RoomGetStateEventError only for the second call
        mock_client_instance.room_get_state_event.side_effect = [
            {},  # This is the response for the first call
            RoomGetStateEventError("Error message"),  # This raises an error for the second call
        ]
        with patch(
            "fractal_database.management.commands.replicate.MatrixClient"
        ) as mock_matrix_client:
            mock_matrix_client.return_value.__aenter__.return_value = mock_client_instance
            command_instance = Command()
            with pytest.raises(CommandError) as e:
                await command_instance._init_instance_db(access_token, homeserver_url, room_id)
            assert (
                str(e.value)
                == "Failed to get database configuration from room state: Error message"
            )
            mock_acurrent.assert_called_once
            mock_client_instance.room_get_state_event.assert_called_with(
                room_id, "f.database.target"
            )


@pytest.mark.skip("Typeerror")
@pytest.mark.django_db
@pytest.mark.asyncio
async def test_replicate_init_instance_db_example_fixture_works_with_aget():
    access_token = "sample_token"
    homeserver_url = "https://homeserver.com"
    room_id = "room_id"

    # Create a real database record
    database = await sync_to_async(Database.objects.create)(name="Test Database")

    # Define a fixture dictionary with the primary key of the database record
    fixture = {"pk": database.pk}

    with patch(
        "fractal_database.management.commands.replicate.Database.current_db",
        side_effect=ObjectDoesNotExist,
    ) as mock_current_db:
        # Mock MatrixClient.room_get_state_event to raise RoomGetStateEventError
        mock_client = MagicMock()
        mock_client.room_get_state_event = MagicMock(
            side_effect=RoomGetStateEventError("Error message")
        )

        # Mock json.loads
        with patch("fractal_database.management.commands.replicate.json.loads") as mock_loads:
            mock_loads.return_value = fixture
            with patch(
                "fractal_database.replication.tasks.replicate_fixture", new=AsyncMock()
            ) as mock_replicate_fixture:
                with patch(
                    "fractal_database.management.commands.replicate.MatrixClient"
                ) as mock_matrixclient:
                    with patch(
                        "fractal_database.management.commands.replicate.Device.objects.get_or_create"
                    ) as mock_get_or_create:
                        # Mock the return value of get_or_create to return a tuple
                        mock_device = MagicMock()
                        mock_get_or_create.return_value = (mock_device, True)
                        mock_matrixclient.return_value = mock_client
                        command_instance = replicate.Command()
                        await command_instance._init_instance_db(
                            access_token=access_token,
                            homeserver_url=homeserver_url,
                            room_id=room_id,
                        )
                        mock_get_or_create.assert_awaited_once()
                        mock_replicate_fixture.assert_called_once_with(fixture)
                        mock_current_db.assert_called_once()
                        mock_matrixclient.assert_called_once_with(
                            homeserver_url, access_token=access_token
                        )
                        Database.objects.aget.assert_awaited_once_with(pk=fixture["pk"])
                        database.aprimary_target.assert_awaited_once()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_replicate_handle_objectdoesnotexist_raise_command_error():
    command_instance = Command()
    with patch("os.environ.get", return_value=None) as mock_get:
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db",
            side_effect=ObjectDoesNotExist,
        ) as mock_current_db:
            with pytest.raises(CommandError) as e:
                await sync_to_async(command_instance.handle)()
            assert "No current database configured. Have you applied migrations?" in str(e.value)


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_replicate_handle_if_no_target():
    database = await sync_to_async(Database.objects.create)(name="Test Database")
    database.primary_target = MagicMock(return_value=None)
    command_instance = Command()
    with patch("os.environ.get", return_value=None) as mock_get:
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db"
        ) as mock_current_db:
            with patch.object(Database, "current_db", return_value=database):
                with pytest.raises(CommandError) as e:
                    await sync_to_async(command_instance.handle)()
                assert (
                    "No primary replication target configured. Have you configured the MatrixReplicationTarget?"
                    in str(e.value)
                )


@pytest.mark.skip("Not Finished")
@pytest.mark.django_db
@pytest.mark.asyncio
async def test_replicate_handle_if_no_roomid_runs_correctly():
    database = await sync_to_async(Database.objects.create)(name="Test Database")
    database.primary_target = MatrixReplicationTarget
    command_instance = Command()
    with patch("os.environ.get", return_value=None) as mock_get:
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db"
        ) as mock_current_db:
            with patch.object(Database, "current_db", return_value=database):
                await sync_to_async(command_instance.handle)()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_replicate_handle_if_roomid_keyerror():
    command_instance = Command()
    with patch("os.environ.get") as mock_get:
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db",
            side_effect=ObjectDoesNotExist,
        ) as mock_current_db:
            print("hey")
