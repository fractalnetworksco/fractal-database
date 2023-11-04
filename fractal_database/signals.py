import logging
import os
import threading
from functools import partial
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.db.models.manager import BaseManager
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

logger = logging.getLogger("django")

_thread_locals = threading.local()

if TYPE_CHECKING:
    from fractal_database.models import Database, ReplicatedModel, ReplicationLog


def enter_signal_handler():
    """Increments the counter indicating we've entered a new signal handler."""
    if not hasattr(_thread_locals, "signal_nesting_count"):
        _thread_locals.signal_nesting_count = 0
    _thread_locals.signal_nesting_count += 1


def exit_signal_handler():
    """Decrements the counter indicating we've exited a signal handler."""
    _thread_locals.signal_nesting_count -= 1


def in_nested_signal_handler():
    """Returns True if we're in a nested signal handler, False otherwise."""
    return getattr(_thread_locals, "signal_nesting_count", 0) > 1


@transaction.atomic
def increment_version(sender, instance, **kwargs) -> None:
    """
    Increments the object version and updates the last_updated_by field to the
    configured owner in settings.py
    """
    instance = sender.objects.select_for_update().get(uuid=instance.uuid)
    # owner = apps.get_model("core", "MatrixAccount").objects.get(matrix_id=OWNER_ID)
    # TODO set last updated by when updating
    instance.update(object_version=F("object_version") + 1)
    return None


def schedule_replication_signal(
    sender: "ReplicationLog", instance: "ReplicationLog", created: bool, raw: bool, **kwargs
) -> None:
    if raw:
        logger.info(f"Loading instance from fixture: {instance}")
        return None

    if not transaction.get_connection().in_atomic_block:
        with transaction.atomic():
            return schedule_replication_signal(sender, instance, created, raw, **kwargs)

    try:
        transaction.on_commit(instance.replicate)
    except Exception as e:
        logger.error(f"Could not apply replication log: {e}")


# @receiver(post_save, sender=RepresentationLog)
# def apply_representation_signal(
#     sender: RepresentationLog, instance: RepresentationLog, created: bool, raw: bool, **kwargs
# ) -> None:
#     if raw:
#         logger.info(f"Loading instance from fixture: {instance}")
#         return None

#     try:
#         instance.apply_representation()
#     except Exception as e:
#         logger.error(f"Could not apply representation log: {e}")


# @receiver(m2m_changed, sender=ReplicatedModel)
# def update_m2m(sender, instance, action: str, **kwargs) -> None:
#     root_space_model = apps.get_model("core", "RootSpace")
#     if action == "post_add":
#         logger.info(f"Update m2m sender: {sender}")
#         logger.info(f"Update m2m instance: {instance}")
#         logger.info(f"Update m2m action: {action}")
#         logger.info(f"Update m2m kwargs: {kwargs}")

#         if kwargs["reverse"]:
#             pass
#         else:
#             for object_uuid in kwargs["pk_set"]:
#                 obj: "Space" = instance.spaces.get(uuid=object_uuid)
#                 RepresentationLog.objects.create(
#                     payload=obj.to_dict(),
#                     ref=instance,
#                     action="add_to_space",
#                     object_version=obj.object_version,
#                 )
#             instance.schedule_replication()

#     elif action == "post_delete":
#         pass

#     return None


def launch_replication_agent(
    sender: "Database", instance: "Database", created: bool, raw: bool, **kwargs
) -> None:
    if instance.database:
        # check which type of replication agent to launch
        target = instance.database.replicationtarget_set.filter(primary=True)[0]
        target.module.launch()
        print(f"Launching replication agent for {instance.database} using {target.module}")


def object_post_save(
    sender: "ReplicatedModel", instance: "ReplicatedModel", created: bool, raw: bool, **kwargs
) -> None:
    if raw:
        logger.info(f"Loading instance from fixture: {instance}")
        return None

    if not transaction.get_connection().in_atomic_block:
        with transaction.atomic():
            return object_post_save(sender, instance, created, raw, **kwargs)

    logger.debug("in atomic block")

    enter_signal_handler()

    increment_version(sender, instance)

    # dependencies = []
    # if created:
    #     dependencies = instance.create_dependencies()

    # logger.info(f"{instance.name} dependencies: {dependencies}")

    try:
        if in_nested_signal_handler():
            return None

        logger.info(f"Outermost post save instance: {instance}")

        from fractal_database.models import Database, ReplicationTarget, RootDatabase

        if isinstance(instance, RootDatabase) or isinstance(instance, Database):
            database = instance
        else:
            database = instance.database
        # create a dummy replication target if none exists so we can replicate when a real target is added
        if not database.replicationtarget_set.exists():
            ReplicationTarget.objects.create(
                name="dummy",
                module="fractal_database.replication_targets.dummy",
                database=database,
                primary=False,
            )
        # create replication log entry for this instance
        instance.schedule_replication()

    finally:
        exit_signal_handler()


def set_object_database(
    sender: "ReplicatedModel", instance: "ReplicatedModel", raw: bool, **kwargs
):
    """
    Set the database for a user defined model
    """
    if raw:
        return

    from fractal_database.models import Database, RootDatabase

    if isinstance(instance, RootDatabase):
        try:
            database = RootDatabase.objects.get()
            raise Exception("Only one root database can exist in a root database")
        except RootDatabase.DoesNotExist:
            instance.database = instance
            return

    try:
        root_database = RootDatabase.objects.get()
        # if this object is a database inside a root database set the database to RootDatabase
        instance.database = root_database
        return
    except RootDatabase.DoesNotExist:
        # in an instance database
        # get the sole Database and set it as the database for this object
        if isinstance(instance, Database):
            try:
                database = Database.objects.get()
                # return if current instance is the sole existing database
                if database == instance:
                    return
                raise Exception("Only one database can exist in an instance database")
            except Database.DoesNotExist:
                return

        # set the database to the sole Database on the user defined model
        database = Database.objects.get()
        instance.database = database


def create_project_database(*args, **kwargs) -> None:
    """
    post_migrate signal to create the default instance Database based on the name of the project
    """
    from fractal_database.models import Database

    project_name = os.path.basename(settings.BASE_DIR)
    Database.objects.get_or_create(name=project_name, defaults={"name": project_name})


def create_matrix_replication_target(*args, **kwargs) -> None:
    """ """
    from fractal_database.models import Database, ReplicationTarget

    project_name = os.path.basename(settings.BASE_DIR)
    module_path = "fractal_database_matrix"
    database = Database.objects.get(name=project_name)
    ReplicationTarget.objects.get_or_create(
        name="matrix",
        defaults={
            "name": "matrix",
            "module": module_path,
            "primary": True,
            "database": database,
            "has_repr": True,
        },
    )
    database.schedule_replication()
