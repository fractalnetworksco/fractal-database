import json
import logging
import os
import socket
import sys

from asgiref.sync import async_to_sync, sync_to_async
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from fractal.cli import FRACTAL_DATA_DIR
from fractal.matrix.async_client import MatrixClient
from fractal_database.models import Database, DatabaseConfig, Device
from fractal_database.utils import get_project_name
from fractal_database_matrix.models import MatrixCredentials, MatrixReplicationTarget
from nio import RoomGetStateEventError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Starts a replication process for the configured database."

    def add_arguments(self, parser):
        # Add command arguments here (optional)
        pass

    async def _init_instance_db(self, access_token: str, homeserver_url: str, room_id: str):
        try:
            database = await Database.acurrent_db()
            # FIXME: Make sure this is right
            print(f"Already have database {database} configured.")
            return database
        except ObjectDoesNotExist:
            pass

        # pull in database from room state
        async with MatrixClient(homeserver_url, access_token) as client:
            db_state_res = await client.room_get_state_event(room_id, "f.database")
            if isinstance(db_state_res, RoomGetStateEventError):
                raise CommandError(
                    f"Failed to get database configuration from room state: {db_state_res.message}"
                )
            target_state_res = await client.room_get_state_event(room_id, "f.database.target")
            if isinstance(target_state_res, RoomGetStateEventError):
                raise CommandError(
                    f"Failed to get database configuration from room state: {target_state_res.message}"
                )
            # FIXME: Put into own function
            from fractal_database_matrix.broker import broker

            broker._init_queues()
            broker.replication_queue.checkpoint.since_token = None
            from fractal_database.replication.tasks import replicate_fixture

            fixture_str = db_state_res.content["fixture"]
            await replicate_fixture(fixture_str)
            database_fixture = json.loads(fixture_str)
            fixture_str = target_state_res.content["fixture"]
            target_fixture = json.loads(fixture_str)
            await replicate_fixture(fixture_str)

        serialized_database = None
        for item in database_fixture:
            if item.get("model") == "fractal_database.database":
                serialized_database = item
                break

        database = await Database.objects.aget(pk=serialized_database["pk"])
        primary_target = await database.aprimary_target()

        # create device for the current instance if it doesn't exist
        device, _ = await Device.objects.aget_or_create(
            name__icontains=socket.gethostname(), defaults={"name": socket.gethostname()}
        )

        await DatabaseConfig.objects.acreate(current_db=database, current_device=device)

        # create matrix credentials for the current device if they don't exist
        try:
            creds = await primary_target.matrixcredentials_set.aget(device=device)
        except MatrixCredentials.DoesNotExist:
            creds = await MatrixCredentials.objects.acreate(
                access_token=access_token, device=device
            )
            await sync_to_async(primary_target.matrixcredentials_set.add)(creds)

        return database

    def handle(self, *args, **options):
        if not os.environ.get("MATRIX_ROOM_ID"):
            try:
                database = Database.current_db()
            except ObjectDoesNotExist:
                raise CommandError("No current database configured. Have you applied migrations?")

            # FIXME: Handle multiple replication targets. For now just using
            # MatrixReplicationTarget
            target = database.primary_target()
            if not target:
                raise CommandError(
                    "No primary replication target configured. Have you configured the MatrixReplicationTarget?"
                )
            elif not isinstance(target, MatrixReplicationTarget):
                raise CommandError(
                    "Only MatrixReplicationTarget primary targets are supported for replication. Found %s"
                    % target.__class__.__name__
                )

            # fetch matrix credentials for current device
            current_device = Device.current_device()
            access_token = target.matrixcredentials_set.get(device=current_device).access_token
            print(f"USING ACCESSTOKEN {access_token}")
            homeserver_url = target.homeserver
            room_id = target.metadata["room_id"]
        else:
            logger.info(
                "MATRIX_ROOM_ID is set in environment. Using environment variables for configuration."
            )
            try:
                room_id = os.environ["MATRIX_ROOM_ID"]
                access_token = os.environ["MATRIX_ACCESS_TOKEN"]
                homeserver_url = os.environ["MATRIX_HOMESERVER_URL"]
            except KeyError as e:
                raise CommandError(
                    f"Missing environment variable {e}. Have you configured the MatrixReplicationTarget?"
                ) from e

            logger.info("Initializing instance database")
            database = async_to_sync(self._init_instance_db)(
                access_token, homeserver_url, room_id
            )

        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")

        project_name = get_project_name()

        process_env = os.environ.copy()
        process_env["MATRIX_ACCESS_TOKEN"] = access_token
        process_env["MATRIX_HOMESERVER_URL"] = homeserver_url
        process_env["MATRIX_ROOM_ID"] = room_id
        process_env["PYTHONPATH"] = (
            os.path.join(FRACTAL_DATA_DIR, project_name)
            + os.pathsep
            + process_env.get("PYTHONPATH", "")
        )
        process_env["DJANGO_SETTINGS_MODULE"] = str(settings_module)

        logger.info(
            "Starting replication process for database %s (syncing from %s/room/%s)"
            % (database, homeserver_url, room_id)
        )

        # launch taskiq worker
        args = [
            sys.executable,
            "-m",
            "taskiq",
            "worker",
            "--ack-type",
            "when_received",
            "fractal_database_matrix.broker:broker",
            "fractal_database.replication.tasks",  # FIXME: may need to use -fsd so we can discover many task types
        ]
        os.execve(
            sys.executable,
            args,
            process_env,
        )
