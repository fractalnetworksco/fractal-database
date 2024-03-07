from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fractal_database.management.commands import replicate
from fractal_database.management.commands.replicate import (
    BaseCommand,
    Command,
    CommandError,
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


@pytest.mark.skip("Stil finishing")
@pytest.mark.asyncio
async def test_init_instance_db_roomgetstateeventerror_raises_commanderror():
    access_token = "sample_token"
    homeserver_url = "https://homeserver.com"
    room_id = "room_id"
    with patch(
        "fractal_database.management.commands.replicate.Database.acurrent_db",
        side_effect=ObjectDoesNotExist,
    ) as mock_acurrent_db:
        with patch(
            "fractal_database.management.commands.replicate.MatrixClient",
        ):
            with patch(
                "nio.client.async_client.AsyncClient.room_get_state_event",
                side_effect=RoomGetStateEventError,
            ) as mock_matrixclient_get_state_event:
                with pytest.raises(CommandError) as e:
                    command_instance = replicate.Command()
                    await replicate.Command._init_instance_db(
                        self=command_instance,
                        access_token=access_token,
                        homeserver_url=homeserver_url,
                        room_id=room_id,
                    )
                assert mock_matrixclient_get_state_event.assert_called_once()
                assert "Failed to get database configuration from room state: " in str(e.value)
