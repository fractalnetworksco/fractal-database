import logging
import os

from django.apps import AppConfig
from django.conf import settings
from django.db import models
from django.db.models.fields.related import ManyToManyField, ManyToManyRel

logger = logging.getLogger(__name__)


class FractalDatabaseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fractal_database"

    def ready(self):
        from fractal_database.models import Database, Device, ReplicatedModel
        from fractal_database.signals import (
            create_database_and_matrix_replication_target,
            join_device_to_database,
            register_device_account,
            schedule_replication_on_m2m_change,
            upload_exported_apps,
        )

        #   Assert that fractal_database is last in INSTALLED_APPS
        self._assert_installation_order()

        models.signals.m2m_changed.connect(
            join_device_to_database, sender=Database.devices.through
        )
        # register replication signals for all models that subclass ReplicatedModel
        ReplicatedModel.connect_signals()

        # create the instance database for the project
        if not os.environ.get("MATRIX_ROOM_ID"):
            # create the matrix replication target for the project database
            models.signals.post_migrate.connect(
                create_database_and_matrix_replication_target, sender=self
            )
        else:
            logger.warning(
                "MATRIX_ROOM_ID is set, not creating database and matrix replication target."
            )

        models.signals.post_migrate.connect(upload_exported_apps, sender=self)
        models.signals.post_save.connect(register_device_account, sender=Device)

        # automatically connect schedule replication signal for replicated models that have
        # many to many fields on them.
        for model in ReplicatedModel.models:
            for field in model._meta.get_fields():
                # skip fields that aren't many to many
                if not isinstance(field, ManyToManyField) and not isinstance(
                    field, ManyToManyRel
                ):
                    continue

                if isinstance(field, ManyToManyField):
                    field_name = field.name
                elif isinstance(field, ManyToManyRel):
                    if field.related_name:
                        field_name = field.related_name
                    else:
                        field_name = f"{field.name}_set"

                through = getattr(model, field_name).through
                if through is not None:
                    models.signals.m2m_changed.connect(
                        schedule_replication_on_m2m_change, sender=through
                    )

    @staticmethod
    def _assert_installation_order():
        try:
            assert settings.INSTALLED_APPS[-1] == "fractal_database"
        except AssertionError as e:
            raise AssertionError(
                """'fractal_database' must be the last entry in INSTALLED_APPS. Please move 'fractal_database' to the end of INSTALLED_APPS in your project's settings.py."""
            ) from e
