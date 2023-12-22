import logging
import os
import threading
from secrets import token_hex
from typing import TYPE_CHECKING, Dict, List
from uuid import UUID

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from fractal.matrix import MatrixClient
from fractal_database.utils import get_project_name

logger = logging.getLogger("django")

_thread_locals = threading.local()

if TYPE_CHECKING:
    from fractal_database.models import (
        Database,
        Device,
        ReplicatedModel,
        ReplicationTarget,
    )
    from fractal_database_matrix.models import MatrixCredentials


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


def commit(target: "ReplicationTarget") -> None:
    """
    Commits a deferred replication for a ReplicationTarget, then removes
    the ReplicationTarget from deferred replications.

    Intended to be called by the transaction.on_commit handler registered
    by defer_replication.
    """
    # this runs its own thread so once this completes, we need to clear the deferred replications
    # for this target
    try:
        print("Inside signals: commit")
        try:
            async_to_sync(target.replicate)()
        except Exception as e:
            logger.error(f"Error replicating {target}: {e}")
    finally:
        clear_deferred_replications(target.name)


def defer_replication(target: "ReplicationTarget") -> None:
    """
    Defers replication of a ReplicationTarget until the current transaction is committed.
    Supports multiple ReplicationTargets per transaction. Replication will only be performed
    once per target.

    Args:
        target (ReplicationTarget): The ReplicationTarget to defer replication.
    """
    if not transaction.get_connection().in_atomic_block:
        raise Exception("Replication can only be deferred inside an atomic block")

    logger.info(f"Deferring replication of {target}")
    if not hasattr(_thread_locals, "defered_replications"):
        _thread_locals.defered_replications = {}
    # only register an on_commit replicate once per target
    if target.name not in _thread_locals.defered_replications:
        logger.info(f"Registering on_commit for {target.name}")
        transaction.on_commit(lambda: commit(target))
    _thread_locals.defered_replications.setdefault(target.name, []).append(target)


def get_deferred_replications() -> Dict[str, List["ReplicationTarget"]]:
    """
    Returns a dict of ReplicationTargets that have been deferred for replication.
    """
    return getattr(_thread_locals, "defered_replications", {})


def clear_deferred_replications(target: str) -> None:
    """
    Clears the deferred replications for a given target.

    Args:
        target (str): The target to clear deferred replications for.
    """
    logger.info("Clearing deferred replications for target %s" % target)
    del _thread_locals.defered_replications[target]


def increment_version(sender, instance, **kwargs) -> None:
    """
    Increments the object version and updates the last_updated_by field to the
    configured owner in settings.py
    """
    # instance = sender.objects.select_for_update().get(uuid=instance.uuid)
    # TODO set last updated by when updating
    instance.update(object_version=F("object_version") + 1)
    instance.refresh_from_db()


def object_post_save(
    sender: "ReplicatedModel", instance: "ReplicatedModel", created: bool, raw: bool, **kwargs
) -> None:
    """
    Schedule replication for a ReplicatedModel instance
    """
    logger.debug("In post save")
    if raw:
        logger.info(f"Loading instance from fixture: {instance}")
        return None

    if not transaction.get_connection().in_atomic_block:
        with transaction.atomic():
            return object_post_save(sender, instance, created, raw, **kwargs)

    logger.debug("in atomic block")

    enter_signal_handler()

    increment_version(sender, instance)

    try:
        if in_nested_signal_handler():
            logger.info(f"Back inside post_save for instance: {instance}")
            return None

        logger.info(f"Outermost post save instance: {instance}")

        # create replication log entry for this instance
        logger.info(f"Calling schedule replication on {instance}")
        instance.schedule_replication(created=created)

    finally:
        exit_signal_handler()


def create_project_database(*args, **kwargs) -> None:
    """
    Runs on post_migrate signal to create the Fractal Database for the Django project
    """
    from fractal_database.models import Database, DatabaseConfig

    project_name = get_project_name()
    logger.info('Creating Fractal Database for Django project "%s"' % project_name)

    d, _ = Database.objects.get_or_create(
        name=project_name,
        defaults={
            "name": project_name,
        },
    )

    DatabaseConfig.objects.get_or_create(
        current_db=d,
        defaults={
            "current_db": d,
        },
    )


def create_matrix_replication_target(*args, **kwargs) -> None:
    """
    Runs on post_migrate signal to setup the MatrixReplicationTarget for the Django project
    """
    from fractal.cli.controllers.authenticated import AuthenticatedController
    from fractal_database.models import Database
    from fractal_database_matrix.models import MatrixReplicationTarget

    creds = AuthenticatedController.get_creds()
    if creds:
        access_token, homeserver_url = creds
    else:
        if not os.environ.get("MATRIX_HOMESERVER_URL") or not os.environ.get(
            "MATRIX_ACCESS_TOKEN"
        ):
            logger.info(
                "MATRIX_HOMESERVER_URL and/or MATRIX_ACCESS_TOKEN not set, skipping MatrixReplicationTarget creation"
            )
            return
        # make sure the appropriate matrix env vars are set
        homeserver_url = os.environ["MATRIX_HOMESERVER_URL"]
        # TODO move access_token to a non-replicated model
        access_token = os.environ["MATRIX_ACCESS_TOKEN"]

    database = Database.current_db()

    logger.info("Creating MatrixReplicationTarget for database %s" % database)
    target, created = MatrixReplicationTarget.objects.get_or_create(
        name="matrix",
        defaults={
            "name": "matrix",
            "primary": True,
            "database": database,
            "homeserver": homeserver_url,
            "access_token": access_token,
        },
    )
    database.schedule_replication()


def ensure_replication_target(*args, **kwargs) -> None:
    from fractal_database.models import Database, DummyReplicationTarget

    database = Database.current_db()
    # create a dummy replication target if none exists so we can replicate when a real target is added

    if not database.get_all_replication_targets():
        DummyReplicationTarget.objects.create(
            name="dummy",
            database=database,
            primary=False,
        )


async def _invite_device(
    device_creds: "MatrixCredentials", database_room_id: str, homeserver_url: str
) -> None:
    access_token = os.environ.get("MATRIX_ACCESS_TOKEN")
    device_matrix_id = device_creds.matrix_id

    async with MatrixClient(
        homeserver_url=homeserver_url,
        access_token=access_token,
    ) as client:
        logger.info("Inviting %s to %s" % (device_matrix_id, database_room_id))
        await client.invite(user_id=device_matrix_id, room_id=database_room_id, admin=True)

    # accept invite on behalf of device
    async with MatrixClient(
        homeserver_url=homeserver_url,
        access_token=device_creds.access_token,
    ) as client:
        logger.info("Accepting invite for %s as %s" % (database_room_id, device_matrix_id))
        await client.join_room(database_room_id)


def join_device_to_database(
    sender: "Database", instance: "Database", pk_set: list[UUID], **kwargs
) -> None:
    from fractal_database.models import Device

    if kwargs["action"] != "post_add":
        return None

    for device_id in pk_set:
        device = Device.objects.get(pk=device_id)
        primary_target = instance.primary_target()

        creds = device.matrixcredentials_set.filter(
            target__homeserver=primary_target.homeserver
        ).get()

        async_to_sync(_invite_device)(
            creds,
            primary_target.metadata["room_id"],
            primary_target.homeserver,
        )


@receiver(post_save, sender="fractal_database.Device")
def register_device_account(
    sender: "Device", instance: "Device", created: bool, raw: bool, **kwargs
) -> None:
    from fractal_database.models import Database
    from fractal_database_matrix.models import MatrixCredentials

    if not created:
        return None

    logger.info("Registering device account for %s" % instance)

    async def _register_device_account() -> tuple[str, str, str]:
        from fractal.matrix import MatrixClient

        async with MatrixClient(
            homeserver_url=os.environ["MATRIX_HOMESERVER_URL"],
            access_token=os.environ["MATRIX_ACCESS_TOKEN"],
        ) as client:
            registration_token = await client.generate_registration_token()
            await client.whoami()
            homeserver_name = client.user_id.split(":")[1]
            matrix_id = f"@{instance.name}:{homeserver_name}"
            password = token_hex(32)
            access_token = await client.register_with_token(
                matrix_id=matrix_id,
                password=password,
                registration_token=registration_token,
                device_name=instance.display_name or instance.name,
            )
            return access_token, matrix_id, password

    access_token, matrix_id, password = async_to_sync(_register_device_account)()
    MatrixCredentials.objects.create(
        matrix_id=matrix_id,
        password=password,
        access_token=access_token,
        target=Database.current_db().primary_target(),
        device=instance,
    )
