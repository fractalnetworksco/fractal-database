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
async def test_init_instance_database_already_configured():
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
async def test_init_instance_db_objectdoesnotexit_pass():
    access_token = "sample_token"
    homeserver_url = "https://homeserver.com"
    room_id = "room_id"

    # Mock every function necessary
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


@pytest.mark.skip("Figuring out how to define a fixture dictionary to test functionality")
@pytest.mark.django_db
@pytest.mark.asyncio
async def test_init_instance_db_example_fixture_works_with_aget():
    access_token = "sample_token"
    homeserver_url = "https://homeserver.com"
    room_id = "room_id"

    # Create a real database record
    database = await sync_to_async(Database.objects.create)(name="Test Database")

    # Define a fixture dictionary with the primary key of the database record
    fixture = {"pk": database.pk}

    # Mock Database.current_db to raise ObjectDoesNotExist
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
            mock_loads.return_value = {}  # You can customize the return value if needed

            # Mock replicate_fixture
            with patch(
                "fractal_database.replication.tasks.replicate_fixture", new=AsyncMock()
            ) as mock_replicate_fixture:
                with patch(
                    "fractal_database.management.commands.replicate.MatrixClient"
                ) as mock_matrixclient:
                    mock_matrixclient.return_value = mock_client

                    command_instance = replicate.Command()
                    with pytest.raises(CommandError) as exc_info:
                        await command_instance._init_instance_db(
                            access_token=access_token,
                            homeserver_url=homeserver_url,
                            room_id=room_id,
                        )

                    assert (
                        str(exc_info.value)
                        == "Failed to get database configuration from room state: Error message"
                    )
                    mock_matrixclient.assert_called_once_with(
                        homeserver_url, access_token=access_token
                    )


@pytest.mark.skip("Figure out why this results in a timeout error on _init_instance_db call")
@pytest.mark.asyncio
async def test_init_instance_db_roomgetstateeventerror_raises_commanderror():
    access_token = "sample_token"
    homeserver_url = "https://homeserver.com"
    room_id = "room_id"
    command_instance = replicate.Command()
    with patch(
        "fractal_database.models.Database.acurrent_db",
        side_effect=ObjectDoesNotExist,
    ) as mock_current_db:
        mock_client = MagicMock()
        mock_client.room_get_state_event = MagicMock(
            side_effect=RoomGetStateEventError("Error message")
        )
        with pytest.raises(CommandError) as exc_info:
            await command_instance._init_instance_db(
                access_token=access_token,
                homeserver_url=homeserver_url,
                room_id=room_id,
            )
        assert (
            exc_info.value.args[0]
            == "Failed to get database configuration from room state: Error message"
        )
        mock_current_db.assert_called_once()
        mock_client.room_get_state_event.assert_called_once_with(room_id, "m.room.create")


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_handle_objectdoesnotexist_raise_command_error():
    command_instance = Command()
    with patch("os.environ.get", return_value=None) as mock_get:
        with patch(
            "fractal_database.management.commands.replicate.Database.acurrent_db",
            side_effect=ObjectDoesNotExist,
        ) as mock_acurrent_db:
            with pytest.raises(CommandError) as e:
                await sync_to_async(command_instance.handle)()
            assert "No current database configured. Have you applied migrations?" in str(e.value)
