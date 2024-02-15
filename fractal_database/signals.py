import logging
import os
import socket
import tarfile
import threading
from secrets import token_hex
from typing import TYPE_CHECKING, Any, Dict, List

from asgiref.sync import async_to_sync
from django.apps import AppConfig
from django.conf import settings
from django.db import transaction
from django.db.models import F
from fractal.matrix import MatrixClient
from fractal_database.utils import get_project_name, init_poetry_project
from taskiq_matrix.lock import MatrixLock

logger = logging.getLogger(__name__)

_thread_locals = threading.local()

if TYPE_CHECKING:
    from fractal_database.models import (
        Database,
        Device,
        ReplicatedModel,
        ReplicationTarget,
    )
    from fractal_database.representations import Representation
    from fractal_database_matrix.models import (
        MatrixCredentials,
        MatrixReplicationTarget,
    )

try:
    FRACTAL_EXPORT_DIR = settings.FRACTAL_EXPORT_DIR
except:
    FRACTAL_EXPORT_DIR = settings.BASE_DIR / "export"


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


def register_device_account(
    sender: "Device", instance: "Device", created: bool, raw: bool, **kwargs
) -> None:
    """
    TODO: This should become a task, so that if it fails we know about it and
    aren't left in a weird state.
    """
    from fractal.cli.controllers.auth import AuthenticatedController
    from fractal_database.models import Database
    from fractal_database_matrix.models import MatrixCredentials

    # TODO: when loading from fixture, a device account should be created
    # only if the device account doesn't already exist on the homeserver.
    if not created or raw:
        return None

    logger.info("Registering device account for %s" % instance.name)

    async def _register_device_account() -> tuple[str, str, str]:
        from fractal.matrix import MatrixClient

        creds = AuthenticatedController.get_creds()
        if creds:
            access_token, homeserver_url, _ = creds
        else:
            access_token = os.environ["MATRIX_ACCESS_TOKEN"]
            homeserver_url = os.environ["MATRIX_HOMESERVER_URL"]

        async with MatrixClient(
            homeserver_url=homeserver_url,
            access_token=access_token,
        ) as client:
            registration_token = await client.generate_registration_token()
            await client.whoami()
            homeserver_name = client.user_id.split(":")[1]
            matrix_id = f"@{instance.name}:{homeserver_name}"
            # FIXME: prompt for user master password here so that we can
            # deterministically generate the device password
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


def schedule_replication_on_m2m_change(
    sender: "ReplicatedModel",
    instance: "ReplicatedModel",
    action: str,
    reverse: bool,
    model: "ReplicatedModel",
    pk_set: list[Any],
    **kwargs,
) -> None:
    """
    Calls schedule replication on the instance (and its reverse relations) whenever a many to many field is changed.

    Connected via fractal_database.apps.FractalDatabaseConfig.ready
    """
    if action not in {"post_add", "post_remove"}:
        return None

    print(f"Inside schedule_replication_on_m2m_change: {instance}")
    for id in pk_set:
        if reverse:
            related_instance = model.objects.get(pk=id)
            instance.schedule_replication(created=False)
            related_instance.schedule_replication(created=False)
        else:
            related_instance = instance
            related_instance.save()
            # related_instance.schedule_replication(created=False)


def create_database_and_matrix_replication_target(*args, **kwargs) -> None:
    """
    Runs on post_migrate signal to setup the MatrixReplicationTarget for the
    Django project.
    """
    from fractal.cli.controllers.auth import AuthenticatedController
    from fractal_database.models import (
        Database,
        DatabaseConfig,
        Device,
        DummyReplicationTarget,
    )
    from fractal_database_matrix.models import (
        MatrixCredentials,
        MatrixReplicationTarget,
    )

    if not transaction.get_connection().in_atomic_block:
        with transaction.atomic():
            return create_database_and_matrix_replication_target(*args, **kwargs)

    project_name = get_project_name()
    logger.info('Creating Fractal Database for Django project "%s"' % project_name)

    database, _ = Database.objects.get_or_create(
        name=project_name,
        is_root=True,
        defaults={
            "name": project_name,
            "is_root": True,
        },
    )

    # TODO: This needs to also happen in an instance db. Move this to another signal?
    current_db_config, _ = DatabaseConfig.objects.get_or_create(
        current_db=database,
        defaults={
            "current_db": database,
        },
    )
    # create a dummy replication target if none exists so we can replicate when a real target is added
    if not database.get_all_replication_targets():
        DummyReplicationTarget.objects.create(
            name="dummy",
            database=database,
            primary=False,
        )

    creds = AuthenticatedController.get_creds()
    if creds:
        access_token, homeserver_url, owner_matrix_id = creds
    else:
        if (
            not os.environ.get("MATRIX_HOMESERVER_URL")
            or not os.environ.get("MATRIX_ACCESS_TOKEN")
            or not os.environ.get("MATRIX_OWNER_MATRIX_ID")
        ):
            logger.info(
                "MATRIX_HOMESERVER_URL and/or MATRIX_ACCESS_TOKEN not set, skipping MatrixReplicationTarget creation"
            )
            return
        # make sure the appropriate matrix env vars are set
        homeserver_url = os.environ["MATRIX_HOMESERVER_URL"]
        owner_matrix_id = os.environ["MATRIX_OWNER_MATRIX_ID"]
        # TODO move access_token to a non-replicated model
        access_token = os.environ["MATRIX_ACCESS_TOKEN"]

    logger.info("Creating MatrixReplicationTarget for database %s" % database)
    target, created = MatrixReplicationTarget.objects.get_or_create(
        name="matrix",
        database=database,
        defaults={
            "name": "matrix",
            "primary": True,
            "database": database,
            "homeserver": homeserver_url,
        },
    )

    device_name = f"{socket.gethostname()}_{token_hex(4)}".lower()
    device, created = Device.objects.get_or_create(
        name=device_name,
        owner_matrix_id=owner_matrix_id,
        display_name=device_name,
        defaults={
            "name": device_name,
            "owner_matrix_id": owner_matrix_id,
            "display_name": device_name,
        },
    )
    current_db_config.update(current_device=device)
    database.devices.add(device)

    # replicate the database now that we have a replication target
    print(f"Replicating after adding device to database")
    database.save()
    # database.schedule_replication()


async def _accept_invite(
    device_creds: "MatrixCredentials", database_room_id: str, homeserver_url: str
):
    device_matrix_id = device_creds.matrix_id
    # accept invite on behalf of device
    async with MatrixClient(
        homeserver_url=homeserver_url,
        access_token=device_creds.access_token,
    ) as client:
        logger.info("Accepting invite for %s as %s" % (database_room_id, device_matrix_id))
        await client.join_room(database_room_id)


async def _invite_device(
    device_creds: "MatrixCredentials", database_room_id: str, homeserver_url: str
) -> None:
    from fractal.cli.controllers.auth import AuthenticatedController

    # TODO: Once user has accounts on many homeservers, we need to try all
    # creds until we find the one that works.
    creds = AuthenticatedController.get_creds()
    if creds:
        access_token, user_homeserver_url, owner_matrix_id = creds
    access_token = os.environ.get("MATRIX_ACCESS_TOKEN")
    device_matrix_id = device_creds.matrix_id

    async with MatrixClient(
        homeserver_url=user_homeserver_url,
        access_token=access_token,
    ) as client:
        logger.info("Inviting %s to %s" % (device_matrix_id, database_room_id))
        await client.invite(user_id=device_matrix_id, room_id=database_room_id, admin=True)


def join_device_to_database(
    sender: "Database", instance: "Database", pk_set: list[Any], **kwargs
) -> None:
    """
    When a new device is added to a database, this signal sends an invite
    to the added device and automatically accepts it.
    """
    from fractal_database.models import Device

    if kwargs["action"] != "post_add":
        return None

    current_device = Device.current_device()

    for device_id in pk_set:
        # dont send an invite if the device is the current device
        # since the current device is invited in create_representation
        if device_id == current_device.pk:
            continue

        device = Device.objects.get(pk=device_id)
        primary_target = instance.primary_target()

        device_creds = device.matrixcredentials_set.filter(
            target__homeserver=primary_target.homeserver  # type: ignore
        ).get()

        async_to_sync(_invite_device)(
            device_creds,
            primary_target.metadata["room_id"],  # type: ignore
            primary_target.homeserver,  # type: ignore
        )
        async_to_sync(_accept_invite)(
            device_creds,
            primary_target.metadata["room_id"],  # type: ignore
            primary_target.homeserver,  # type: ignore
        )
        # accept invite on behalf of device


async def _lock_and_put_state(
    repr_instance: "Representation",
    room_id: str,
    target: "MatrixReplicationTarget",
    state_type: str,
    content: dict[str, Any],
) -> None:
    """
    Acquires a lock for the given state_type and puts the state in the provided room.
    """
    from fractal.cli.controllers.auth import AuthenticatedController

    creds = AuthenticatedController.get_creds()
    if creds:
        access_token, homeserver_url, owner_matrix_id = creds
    else:
        raise Exception("No creds found not locking and putting state")

    async with MatrixLock(homeserver_url, access_token, room_id).lock(key=state_type) as lock_id:  # type: ignore
        await repr_instance.put_state(room_id, target, state_type, content)


def update_target_state(
    sender: "ReplicatedModel", instance: "ReplicatedModel", created: bool, raw: bool, **kwargs
) -> None:
    """
    Updates the state for f.database or f.database.target whenever a
    Database or MatrixReplicationTarget is saved.
    """
    from fractal_database.models import Database, RepresentationLog
    from fractal_database_matrix.models import MatrixReplicationTarget

    # dont do anything if loading from fixture or a new object is created
    if not isinstance(instance, (Database, MatrixReplicationTarget)) or raw or created:
        return None

    logger.info("Updating target state for %s" % instance)
    # only update the state if the object is the primary target
    if isinstance(instance, MatrixReplicationTarget) and not instance.primary:
        return None
    elif isinstance(instance, Database):
        target = instance.primary_target()
        if not target or not isinstance(target, MatrixReplicationTarget):
            logger.warning(
                "Cannot update target state, no primary target found for database %s" % instance
            )
            return None
    else:
        target = instance

    room_id = target.metadata.get("room_id")
    if not room_id:
        logger.warning("Cannot update target state, no room_id found for target %s" % target)
        return None

    instance_fixture = instance.to_fixture(json=True)
    representation_module = target.get_representation_module()
    print(f"Got representation module: {representation_module}")
    repr_instance = RepresentationLog._get_repr_instance(representation_module)
    state_type = "f.database" if isinstance(instance, Database) else "f.database.target"
    # put state needs the matrix credentials for the target so accessing the creds here
    # ensures that the creds are loaded into memory (avoiding lazy loading issues in async)
    # target.matrixcredentials_set

    async_to_sync(_lock_and_put_state)(
        repr_instance, room_id, target, state_type, {"fixture": instance_fixture}
    )


def zip_django_app(sender: AppConfig, *args, **kwargs) -> None:
    """
    Creates a tarball of the `sender` app.

    TODO: Figure out the end user interface for this. Should the user
    connect this signal in their app's ready function?
    FIXME: Namespace packages (things like `mypackage.app`) don't seem to
    work correctly yet. These packages have dots in their names
    and packages wont install correctly due to their name.
    Ideally you would use `packages = [{include="mypackage"}]` instead.
    """
    app_path = sender.path
    app_name = sender.name

    # ensure export directory exists
    os.makedirs(FRACTAL_EXPORT_DIR, exist_ok=True)

    with tarfile.open(f"{FRACTAL_EXPORT_DIR}/{app_name}.tar.gz", "w:gz") as tar:
        # extract everything excluding __pycache__ or any dirs/files that start with . or end with .pyc
        for root, dirs, files in os.walk(app_path):
            dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
            files = [f for f in files if not f.startswith(".") and not f.endswith(".pyc")]

            # Adjust the arcname to prefix with app_name so that the archive is
            # extracted into a directory with the app name
            for file in files:
                file_path = os.path.join(root, file)
                tar.add(
                    file_path,
                    arcname=os.path.join(app_name, os.path.relpath(file_path, app_path)),
                )

            # create an in memory file to create pyproject.toml for the app
            # if the app doesn't already have a pyproject.toml
            if not os.path.exists(f"{app_path}/pyproject.toml"):
                pyproject_file = init_poetry_project(app_name, in_memory=True)
                tarinfo = tarfile.TarInfo("pyproject.toml")
                tarinfo.size = len(pyproject_file.getvalue())
                tar.addfile(tarinfo=tarinfo, fileobj=pyproject_file)

    logger.info("Created tarball of %s" % app_name)


def upload_exported_apps(*args, **kwargs) -> None:
    """
    Uploads all the apps in the export directory to the primary target for
    the current database.
    """
    try:
        apps = os.listdir(FRACTAL_EXPORT_DIR)
    except FileNotFoundError:
        logger.info("No apps found in export directory. Skipping upload")
        return None

    from fractal_database.models import Database, RepresentationLog
    from fractal_database_matrix.models import MatrixReplicationTarget

    try:
        database = Database.current_db()
    except Database.DoesNotExist:
        logger.warning("No current database found, skipping app upload")
        return None

    primary_target = database.primary_target()
    if not primary_target or not isinstance(primary_target, MatrixReplicationTarget):
        logger.warning("No primary target found, skipping app upload")
        return None

    representation_module = primary_target.get_representation_module()
    repr_instance = RepresentationLog._get_repr_instance(representation_module)

    async def _upload_app(room_id: str, app: str) -> None:
        creds = primary_target.get_creds()
        async with MatrixClient(
            homeserver_url=primary_target.homeserver,
            access_token=creds.access_token,
        ) as client:
            mxc_uri = await client.upload_file(
                f"{FRACTAL_EXPORT_DIR}/{app}",
                filename=app,
            )

            # remove the .tar.gz part of the app name
            app_name = app.split(".tar.gz")[0]
            state_type = f"f.database.app.{app_name}"

            await _lock_and_put_state(
                repr_instance, room_id, primary_target, state_type, {"mxc": mxc_uri}
            )
            logger.info("Uploaded %s to %s" % (app, primary_target.homeserver))

    room_id = primary_target.metadata["room_id"]

    # get all the apps in the export directory
    for app_name in apps:
        if not app_name.endswith(".tar.gz"):
            continue
        logger.info(f"Uploading {app_name} to {primary_target.homeserver}")
        async_to_sync(_upload_app)(room_id, app_name)

        # remove the app after uploading (maybe we keep this?)
        # os.remove(f"{FRACTAL_EXPORT_DIR}/{app_name}")
