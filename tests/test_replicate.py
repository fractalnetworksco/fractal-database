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

pytestmark = pytest.mark.django_db(transaction=True)


async def test_replicate_init_instance_database_already_configured(test_database):
    access_token = "sample_token"
    homeserver_url = "https://homeserver.com"
    room_id = "room_id"
    command_instance = replicate.Command()
    instance_database = await replicate.Command._init_instance_db(
        self=command_instance,
        access_token=access_token,
        homeserver_url=homeserver_url,
        room_id=room_id,
    )
    assert instance_database == test_database


async def test_replicate_init_instance_db_success(
    instance_database_room, test_user_access_token, test_homeserver_url
):
    # instance_database_room is a fixture that creates a database and returns the room_id
    # for where the database was replicated. Right before returning this room_id, the database
    # is cleared so that we can load the database from the room state.
    room_id = instance_database_room

    # verify that there isn't a current database configured
    with pytest.raises(Database.DoesNotExist):
        await Database.acurrent_db()

    command = replicate.Command()

    # init instance db should load in the database from the room state
    # as the current database
    loaded_database = await command._init_instance_db(
        test_user_access_token, test_homeserver_url, room_id
    )

    assert isinstance(loaded_database, Database)

    current_database = await Database.acurrent_db()
    assert current_database == loaded_database

    assert False, "Verify that the primary target is loaded in"

<<<<<<< HEAD
    # assert False, "Verify that a DatabaseConfig object is created"

    # assert (
    # False
    # ), "Verify that a MatrixCredentials object is created for the current device and added to the primary_target that was loaded in"
=======
    assert False, "Verify that a DatabaseConfig object is created"

    assert (
        False
    ), "Verify that a MatrixCredentials object is created for the current device and added to the primary_target that was loaded in"
>>>>>>> f4c2685f40abe2f4132fbc0af34d3b0e6a2a0912


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


<<<<<<< HEAD
=======
# Dont need this since the success case will run all of thi
@pytest.mark.skip(
    "Don't need this test since the success case (test_replicate_init_instance_db_success) will run all of this"
)
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


>>>>>>> f4c2685f40abe2f4132fbc0af34d3b0e6a2a0912
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


@pytest.mark.skip("Duplicate to the test above?")
async def test_replicate_handle_if_current_db_raises_object_does_not_exist():
    # Test scenario where current_db raises ObjectDoesNotExist
    mock_current_db = MagicMock(side_effect=ObjectDoesNotExist)
    with patch("os.environ.get", return_value=None) as mock_get:
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db", mock_current_db
        ):
            command_instance = Command()
            with pytest.raises(CommandError) as e:
                await sync_to_async(command_instance.handle)()
            assert "No current database configured. Have you applied migrations?" in str(e.value)


async def test_replicate_handle_if_current_db_returns_valid_database_with_no_target():
    # Test scenario where current_db returns a valid database object with no target
    mock_database = MagicMock()
    mock_database.primary_target.return_value = None
    mock_current_db = MagicMock(return_value=mock_database)
    with patch("os.environ.get", return_value=None) as mock_get:
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db", mock_current_db
        ):
            command_instance = Command()
            with pytest.raises(CommandError) as e:
                await sync_to_async(command_instance.handle)()
            assert (
                "No primary replication target configured. Have you configured the MatrixReplicationTarget?"
                in str(e.value)
            )


async def test_replicate_handle_if_primary_target_not_none():
    mock_primary_target = MagicMock(return_value="MockReplicationTarget")

    mock_database = MagicMock()
    mock_database.primary_target = mock_primary_target
    mock_current_db = MagicMock(return_value=mock_database)

    with patch("os.environ.get", return_value=None) as mock_get:
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db", mock_current_db
        ):
            command_instance = Command()
            with pytest.raises(CommandError) as e:
                await sync_to_async(command_instance.handle)()
            assert (
                "Only MatrixReplicationTarget primary targets are supported for replication"
                in str(e.value)
            )


@pytest.mark.skip("What's being tested here?")
@pytest.mark.django_db
async def test_replicate_handle_current_device():
<<<<<<< HEAD
    target = await sync_to_async(MatrixReplicationTarget.objects.acreate)(
=======

    # FIXME: use acreate instead of create
    target = await sync_to_async(MatrixReplicationTarget.objects.create)(
>>>>>>> f4c2685f40abe2f4132fbc0af34d3b0e6a2a0912
        homeserver="example_homeserver_url",
        metadata={"room_id": "example_room_id"},
    )

    mock_database = MagicMock()
    mock_database.primary_target = target
    mock_current_db = MagicMock(return_value=mock_database)

    with patch("os.environ.get", return_value=None) as mock_get:
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db", mock_current_db
        ):
            command_instance = Command()
            await sync_to_async(command_instance.handle)()


@pytest.mark.skip("Infinite loop. Need to patch os.execve")
@pytest.mark.django_db
async def test_replicate_handle_works_correctly():
    # Mock the primary target and database
    mock_target = MagicMock(spec=MatrixReplicationTarget)
    mock_primary_target = MagicMock(return_value=mock_target)
    mock_database = MagicMock()
    mock_database.primary_target = mock_primary_target

    mock_current_db = MagicMock(return_value=mock_database)
    mock_current_device = MagicMock(return_value="current_device")

    with patch("os.environ.get", return_value=None) as mock_get:
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db", mock_current_db
        ):
            with patch("fractal_database.models.Device.current_device", mock_current_device):
                command_instance = Command()
                await sync_to_async(command_instance.handle)()


async def test_replicate_handle_if_primary_target_not_none_keyerror():
    mock_current_db = MagicMock(side_effect=ObjectDoesNotExist)
    mock_environ = {"MATRIX_ROOM_ID": "test_room_id", "MATRIX_ACCESS_TOKEN": "test_access_token"}
    with patch("os.environ", mock_environ):
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db", mock_current_db
        ):
            command_instance = Command()
            with pytest.raises(CommandError) as e:
                await sync_to_async(command_instance.handle)()
            assert "Missing environment variable 'MATRIX_HOMESERVER_URL'" in str(e.value)
            assert isinstance(e.value.__cause__, KeyError)


@pytest.mark.skip("Infinite Loop - Need to patch os.execve")
async def test_replicate_handle_with_env_set():
    mock_target = MagicMock(spec=MatrixReplicationTarget)

    mock_environ = {
        "MATRIX_ROOM_ID": "test_room_id",
        "MATRIX_ACCESS_TOKEN": "test_access_token",
        "MATRIX_HOMESERVER_URL": "test_homeserver_url",
    }

    with patch("os.environ", mock_environ):
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db",
            return_value=mock_target,
        ) as mock_current_db:
            with patch(
                "fractal_database.management.commands.replicate.Command._init_instance_db"
            ) as mock_instance_db:
                command_instance = Command()
                await sync_to_async(command_instance.handle)()
                mock_current_db.assert_not_called()  # Ensure current_db is not called when env variables are set


@pytest.mark.skip("Infinite Loop. Need to patch os.execve")
@pytest.mark.asyncio
async def test_replicate_handle_if_primary_target_not_none_works():
    with patch(
        "fractal_database.management.commands.replicate.Database.current_db",
        side_effect=ObjectDoesNotExist,
    ) as mock_current_db:
        mock_environ = {
            "MATRIX_ROOM_ID": "test_room_id",
            "MATRIX_ACCESS_TOKEN": "test_access_token",
            "MATRIX_HOMESERVER_URL": "test_homeserver_url",
        }
        with patch("os.environ", mock_environ):
            with patch(
                "fractal_database.management.commands.replicate.Command._init_instance_db"
            ) as mock_init_instance_db:
                command_instance = Command()
                await sync_to_async(command_instance.handle)()
                mock_current_db.assert_called_once()
                mock_init_instance_db.assert_called_once_with(
                    "test_access_token", "test_homeserver_url", "test_room_id"
                )


@pytest.mark.skip("Infinite Loop. Need to patch os.execve")
async def test_replicate_handle_python_path():
    mock_current_db = MagicMock(side_effect=ObjectDoesNotExist)
    mock_environ = {
        "MATRIX_ROOM_ID": "test_room_id",
        "MATRIX_ACCESS_TOKEN": "test_access_token",
        "MATRIX_HOMESERVER_URL": "test_homeserver_url",
    }
    with patch("os.environ", mock_environ):
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db", mock_current_db
        ):
            with patch(
                "fractal_database.management.commands.replicate.Command._init_instance_db"
            ):
                command_instance = Command()
                await sync_to_async(command_instance.handle)()
