from django.apps import AppConfig
from django.db import models


class FractalDatabaseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fractal_database"

    def ready(self):
        from fractal_database.models import Database, ReplicationLog, RootDatabase
        from fractal_database.signals import schedule_replication_signal

        # connect signals here to avoid circular imports
        models.signals.post_save.connect(schedule_replication_signal, sender=ReplicationLog)
