import os
import sys

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from fractal_database.models import Database
from fractal_database_matrix.models import MatrixReplicationTarget


class Command(BaseCommand):
    help = "Starts a replication process for the configured database."

    def add_arguments(self, parser):
        # Add command arguments here (optional)
        pass

    def handle(self, *args, **options):
        if not os.environ.get("MATRIX_ROOM_ID"):
            try:
                database = Database.objects.get(is_self=True)
            except ObjectDoesNotExist:
                raise CommandError("No database configured. Have you applied migrations?")

            # FIXME: Handle multiple replication targets. For now just using
            # MatrixReplicationTarget
            target = database.primary_target
            access_token = target.access_token
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
