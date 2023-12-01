import os
import sys

from django.core.management.base import BaseCommand, CommandError
from fractal_database.models import Database, ReplicatedModelRepresentation
from fractal_database_matrix.models import MatrixReplicationTarget


class Command(BaseCommand):
    help = "Starts a replication process for the configured database."

    def add_arguments(self, parser):
        # Add command arguments here (optional)
        pass

    def handle(self, *args, **options):
        # TODO: handle RootDatabase
        try:
            database = Database.objects.get()
        except Database.DoesNotExist:
            raise CommandError("No database configured. Have you applied migrations?")

        representation = ReplicatedModelRepresentation.objects.get(object_id=database.uuid)
        room_id = representation.metadata["room_id"]

        # FIXME: Handle multiple replication targets. For now just using
        # MatrixReplicationTarget
        target = MatrixReplicationTarget.objects.get(database_id=database.uuid)
        access_token = target.access_token
        homeserver_url = target.homeserver
        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")

        process_env = os.environ.copy()
        process_env["MATRIX_ACCESS_TOKEN"] = access_token
        process_env["MATRIX_HOMESERVER_URL"] = homeserver_url
        process_env["MATRIX_ROOM_ID"] = room_id
        process_env["DJANGO_SETTINGS_MODULE"] = str(settings_module)

        # launch taskiq worker
        print(f"sys.executable: {sys.executable}")
        args = [sys.executable, "-m", "taskiq"] + [
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
