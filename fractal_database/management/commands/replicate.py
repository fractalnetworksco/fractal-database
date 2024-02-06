import socket
import json
import os
import sys

from django.core.exceptions import ObjectDoesNotExist
from fractal.matrix.async_client import MatrixClient
from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError
from fractal_database.models import Database, Device, DatabaseConfig
from fractal_database_matrix.models import MatrixReplicationTarget, MatrixCredentials
from nio import RoomGetStateEventError


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
            return
        except ObjectDoesNotExist:
            pass

        # pull in database from room state
        async with MatrixClient(homeserver_url, access_token) as client:
            db_state_res = await client.room_get_state_event(room_id, "f.database")
            if isinstance(db_state_res, RoomGetStateEventError):
                raise CommandError(
                    f"Failed to get database configuration from room state: {db_state_res.message}"
                )
            target_state_res = await client.room_get_state_event(room_id, "f.database")
            if isinstance(target_state_res, RoomGetStateEventError):
                raise CommandError(
                    f"Failed to get database configuration from room state: {target_state_res.message}"
                )
            # FIXME: Put into own function
            from fractal_database_matrix.broker import broker
            broker._init_queues()
            broker.replication_queue.checkpoint.since_token = None
            from fractal_database.replication.tasks import replicate_fixture
            fixture_str = db_state_res.content['fixture']
            fixture = json.loads(fixture_str)
            await replicate_fixture(fixture)
            fixture_str = target_state_res.content['fixture']
            fixture = json.loads(fixture_str)
            await replicate_fixture(fixture)

        database = await Database.objects.aget(pk=fixture["pk"])
        target = await database.aprimary_target()

        await DatabaseConfig.objects.acreate(current_db=database)

        device, _created = Device.objects.get_or_create(
            name=socket.gethostname(), defaults={"name": socket.gethostname()}
        )
        MatrixCredentials.objects.get_or_create(
            # access_token=access_token,
            target=target,
            # device=device,
            defaults={"access_token": access_token, "target": target, "device": device},
        )

    def handle(self, *args, **options):
        if not os.environ.get("MATRIX_ROOM_ID"):
            try:
                database = Database.current_db()
            except ObjectDoesNotExist:
                raise CommandError("No current database configured. Have you applied migrations?")

            # FIXME: Handle multiple replication targets. For now just using
            # MatrixReplicationTarget
            target = database.primary_target()
            if not target or not isinstance(target, MatrixReplicationTarget):
                raise CommandError(
                    "No primary replication target configured. Have you configured the MatrixReplicationTarget?"
                )

            access_token = target.matrixcredentials.access_token
            homeserver_url = target.homeserver
            room_id = target.metadata["room_id"]
        else:
            try:
                room_id = os.environ["MATRIX_ROOM_ID"]
                access_token = os.environ["MATRIX_ACCESS_TOKEN"]
                homeserver_url = os.environ["MATRIX_HOMESERVER_URL"]
            except KeyError as e:
                raise CommandError(
                    f"Missing environment variable {e}. Have you configured the MatrixReplicationTarget?"
                ) from e

            async_to_sync(self._init_instance_db)(access_token, homeserver_url, room_id)

        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")

        process_env = os.environ.copy()
        process_env["MATRIX_ACCESS_TOKEN"] = access_token
        process_env["MATRIX_HOMESERVER_URL"] = homeserver_url
        process_env["MATRIX_ROOM_ID"] = room_id
        process_env["DJANGO_SETTINGS_MODULE"] = str(settings_module)

        # launch taskiq worker
        args = [
            sys.executable,
            "-m",
            "taskiq",
            "worker",
            "--ack-type",
            "when_received",
            "fractal_database_matrix.broker:broker",
            "fractal_database.replication.tasks",
        ]
        os.execve(
            sys.executable,
            args,
            process_env,
        )
