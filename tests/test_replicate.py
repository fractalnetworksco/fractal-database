from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from fractal_database.management.commands import replicate
from fractal_database.management.commands.replicate import (
    BaseCommand,
    Command,
    CommandError,
    Database,
    DatabaseConfig,
    Device,
    MatrixClient,
    MatrixCredentials,
    MatrixReplicationTarget,
    ObjectDoesNotExist,
    RoomGetStateEventError,
    os,
)
from nio.responses import RoomGetStateEventResponse

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

    current_device = await Device.acurrent_device()
    target = await current_database.aprimary_target()

    assert isinstance(target, MatrixReplicationTarget)

    assert await DatabaseConfig.objects.aexists()

    assert await current_device.matrixcredentials_set.aexists()
    assert (
        await current_device.matrixcredentials_set.aexists()
        == await target.matrixcredentials_set.aexists()
    )


async def test_replicate_init_instance_db_roomgetstateeventerror_raises_commanderror(
    instance_database_room, test_user_access_token, test_homeserver_url
):
    room_id = instance_database_room

    command_instance = Command()

    with patch(
        "nio.client.async_client.AsyncClient.room_get_state_event",
        side_effect=[RoomGetStateEventError("Error message")],
    ):
        with pytest.raises(CommandError) as e:
            await command_instance._init_instance_db(
                test_user_access_token, test_homeserver_url, room_id
            )
    assert "Failed to get database configuration from room state: Error message" in str(e.value)


async def test_replicate_init_instance_db_targetstate_roomgetstateeventerror_raises_commanderror(
    instance_database_room, test_user_access_token, test_homeserver_url
):
    room_id = instance_database_room

    command_instance = Command()

    with patch(
        "nio.client.async_client.AsyncClient.room_get_state_event",
        side_effect=[
            {"content": {"fixture": "valid_db_fixture"}},
            RoomGetStateEventError("Error message"),
        ],
    ):
        with pytest.raises(CommandError) as e:
            await command_instance._init_instance_db(
                test_user_access_token, test_homeserver_url, room_id
            )

    assert "Failed to get database configuration from room state: Error message" in str(e.value)


async def test_replicate_handle_objectdoesnotexist_raise_command_error():
    command_instance = Command()
    with patch("os.environ.get", return_value=None) as mock_get:
        with patch(
            "fractal_database.management.commands.replicate.Database.current_db",
            side_effect=ObjectDoesNotExist,
        ):
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
    target = await MatrixReplicationTarget.objects.acreate(
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


# @pytest.mark.skip("Working on testing with actual database")
@pytest.mark.django_db
async def test_replicate_handle_method(instance_database_room):
    os.environ["MATRIX_ROOM_ID"] = instance_database_room

    database = MagicMock(spec=Database)
    database.primary_target.return_value = MagicMock(spec=Device)
    Database.objects.create.return_value = database

    mock_device = MagicMock(spec=Device)
    mock_device.matrixcredentials_set.get().access_token = "test_access_token"
    mock_current_device = MagicMock(return_value=mock_device)

    with patch(
        "fractal_database.management.commands.replicate.Device.current_device",
        mock_current_device,
    ):
        with patch("os.environ.get", return_value=None):
            with patch("os.execve"):
                command_instance = replicate.Command()
                command_instance.handle()

    mock_device.matrixcredentials_set.get.assert_called_once_with(device=mock_device)
    mock_current_device.assert_called_once()
    Database.objects.create.assert_called_once()
    database.primary_target.assert_called_once()


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


# @pytest.mark.skip("Infinite Loop - Need to patch os.execve")
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
                with patch("os.execve"):
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
