from django.apps import AppConfig
from django.conf import settings
from django.db import models


class FractalDatabaseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fractal_database"

    def ready(self):
        from fractal_database.models import ReplicatedModel, ReplicationLog
        from fractal_database.signals import (
            create_matrix_replication_target,
            create_project_database,
            schedule_replication_signal,
        )

        #   Assert that fractal_database is last in INSTALLED_APPS
        self._assert_installation_order()

        # register ReplicationLog signals here to avoid circular imports
        models.signals.post_save.connect(schedule_replication_signal, sender=ReplicationLog)

        # register replication signals for all models that subclass ReplicatedModel
        ReplicatedModel.connect_signals()

        # create the instance database for the project
        models.signals.post_migrate.connect(create_project_database, sender=self)

        # create the matrix replication target for the project database
        models.signals.post_migrate.connect(create_matrix_replication_target, sender=self)

    @staticmethod
    def _assert_installation_order():
        try:
            assert settings.INSTALLED_APPS[-1] == "fractal_database"
        except AssertionError as e:
            raise AssertionError(
                """Fractal Database requires the 'fractal_database' Django app to be positioned as the final entry in your Django's
 project 'INSTALLED_APPS' in settings.py. This ensures 'fractal_database' is loaded last, allowing it to properly capture and replicate
 database changes. Please adjust the order in 'INSTALLED_APPS' to place 'fractal_database' at the end."""
            ) from e
