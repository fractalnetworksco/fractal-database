import os

from django.apps import AppConfig
from django.conf import settings
from django.db import models


class FractalDatabaseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fractal_database"

    def ready(self):
        from fractal_database.models import ReplicatedModel
        from fractal_database.signals import (
            create_matrix_replication_target,
            create_project_database,
        )

        #   Assert that fractal_database is last in INSTALLED_APPS
        self._assert_installation_order()

        # register replication signals for all models that subclass ReplicatedModel
        ReplicatedModel.connect_signals()

        # create the instance database for the project
        if not os.environ.get("MATRIX_ROOM_ID"):
            models.signals.post_migrate.connect(create_project_database, sender=self)

            # create the matrix replication target for the project database
            models.signals.post_migrate.connect(create_matrix_replication_target, sender=self)

    @staticmethod
    def _assert_installation_order():
        try:
            assert settings.INSTALLED_APPS[-1] == "fractal_database"
        except AssertionError as e:
            raise AssertionError(
                """'fractal_database' must be the last entry in INSTALLED_APPS. Please move 'fractal_database' to the end of INSTALLED_APPS in your project's settings.py."""
            ) from e
