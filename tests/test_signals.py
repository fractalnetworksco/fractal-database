import os
import random
import secrets
import socket
import tarfile
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.apps import AppConfig
from django.conf import settings
from django.db import transaction
from fractal.cli.controllers.auth import AuthenticatedController
from fractal.matrix.async_client import MatrixClient
from fractal_database.models import (
    Database,
    DatabaseConfig,
    Device,
    DummyReplicationTarget,
)
from fractal_database.representations import Representation
from fractal_database.signals import (
    FRACTAL_EXPORT_DIR,
    _accept_invite,
    _invite_device,
    _lock_and_put_state,
    _upload_app,
    get_deferred_replications,
    clear_deferred_replications,
    commit,
    create_database_and_matrix_replication_target,
    defer_replication,
    enter_signal_handler,
    increment_version,
    join_device_to_database,
    object_post_save,
    register_device_account,
    schedule_replication_on_m2m_change,
    update_target_state,
    upload_exported_apps,
    zip_django_app,
)
from fractal_database_matrix.models import MatrixReplicationTarget
from nio import RoomGetStateResponse
from taskiq_matrix.lock import LockAcquireError

pytestmark = pytest.mark.django_db(transaction=True)

FILE_PATH = "fractal_database.signals"


class NotDatabaseOrReplTarget:
    """
    This class is neither a Database or MatrixReplicationTarget subclass.
    Used for forced False isinstance checks.
    """


def test_signals_enter_signal_handler_no_nesting_count():
    """
    Tests that if the _thread_locals object does not have a signal_nesting_count attribute,
    one is created for it an incremented to 1.
    """


    with patch(f"{FILE_PATH}._thread_locals", new=MagicMock()) as mock_thread:
        delattr(mock_thread, "signal_nesting_count")

        assert not hasattr(mock_thread, "signal_nesting_count")
        enter_signal_handler()
        assert hasattr(mock_thread, "signal_nesting_count")
        assert mock_thread.signal_nesting_count == 1


def test_signals_enter_signal_handler_existing_nesting_count():
    """
    Tests that if there is already an existing signal count, it is incremented and is not
    equal to 1.
    """

    # generate a random nest count
    nest_count = random.randint(1, 100)

    # patch thread locals
    with patch(f"{FILE_PATH}._thread_locals", new=MagicMock()) as mock_thread:
        # set the signal nesting count equal to the random number
        mock_thread.signal_nesting_count = nest_count
        # call the function
        enter_signal_handler()

    # verify that the new nest count is equal to the random number + 1
    assert mock_thread.signal_nesting_count == nest_count + 1


def test_signals_commit_replication_error():
    """ 
    
    """

    mock_target = MagicMock(spec=DummyReplicationTarget)
    mock_target.name = "test_name"
    mock_target.replicate = AsyncMock()

    mock_target.replicate.side_effect = Exception()

    with patch(f"{FILE_PATH}.logger", new=MagicMock()) as mock_logger:
        with patch(f"{FILE_PATH}.clear_deferred_replications", new=MagicMock()) as mock_clear:
            commit(mock_target)

    mock_clear.assert_called_with(mock_target.name)
    mock_logger.error.assert_called()


def test_signals_commit_no_error():
    """ """

    repl_target = DummyReplicationTarget()
    repl_target.name = "test_name"

    with patch(f"{FILE_PATH}.logger", new=MagicMock()) as mock_logger:
        with patch(f"{FILE_PATH}.clear_deferred_replications", new=MagicMock()) as mock_clear:
            commit(repl_target)

    mock_clear.assert_called_with(repl_target.name)
    mock_logger.error.assert_not_called()


def test_signals_defer_replication_not_in_transaction():
    """ """

    mock_target = MagicMock(spec=DummyReplicationTarget)
    mock_target.name = "test_name"

    with patch(f"{FILE_PATH}.transaction", new=MagicMock()) as mock_transaction:
        mock_transaction.get_connection = MagicMock()
        mock_transaction.get_connection.return_value = MagicMock()
        mock_transaction.get_connection.return_value.in_atomic_block = False
        with pytest.raises(Exception):
            defer_replication(mock_target)



def test_signals_defer_replication_no_defered_replications():
    """ """

    mock_target = MagicMock(spec=DummyReplicationTarget)
    mock_target.name = "test_name"

    with patch(f"{FILE_PATH}.transaction", new=MagicMock()) as mock_transaction:
        mock_transaction.get_connection = MagicMock()
        mock_transaction.get_connection.return_value = MagicMock()
        mock_transaction.get_connection.return_value.in_atomic_block = True

        with patch(f"{FILE_PATH}._thread_locals") as mock_thread_locals:
            with patch(f"{FILE_PATH}.logger", new=MagicMock()) as mock_logger:
                delattr(mock_thread_locals, "defered_replications")
                defer_replication(mock_target)

    mock_logger.info.assert_called_with(f"Registering on_commit for {mock_target.name}")
    mock_transaction.on_commit.assert_called_once()
    assert "test_name" in mock_thread_locals.defered_replications
    assert mock_thread_locals.defered_replications["test_name"][0] == mock_target
    assert get_deferred_replications() == {}


def test_signals_defer_replication_target_in_defered_replications():
    """ """

    mock_target = MagicMock(spec=DummyReplicationTarget)
    mock_target.name = secrets.token_hex(8)

    with patch(f"{FILE_PATH}.transaction", new=MagicMock()) as mock_transaction:
        mock_transaction.get_connection = MagicMock()
        mock_transaction.get_connection.return_value = MagicMock()
        mock_transaction.get_connection.return_value.in_atomic_block = True

        with patch(f"{FILE_PATH}._thread_locals") as mock_thread_locals:
            with patch(f"{FILE_PATH}.logger", new=MagicMock()) as mock_logger:
                mock_thread_locals.defered_replications = {mock_target.name: [mock_target]}
                defer_replication(mock_target)

    mock_logger.info.assert_called_once()
    mock_transaction.on_commit.assert_not_called()
    assert mock_target.name in mock_thread_locals.defered_replications
    assert mock_thread_locals.defered_replications[mock_target.name][0] == mock_target

    # accessing index 1 to verify that defer_replication adds the given target to the list
    assert mock_thread_locals.defered_replications[mock_target.name][1] == mock_target


def test_signals_clear_defered_replications_functional_test():
    """ """

    mock_target = MagicMock(spec=DummyReplicationTarget)
    mock_target.name = secrets.token_hex(8)

    with patch(f"{FILE_PATH}.transaction", new=MagicMock()) as mock_transaction:
        mock_transaction.get_connection = MagicMock()
        mock_transaction.get_connection.return_value = MagicMock()
        mock_transaction.get_connection.return_value.in_atomic_block = True

        with patch(f"{FILE_PATH}._thread_locals") as mock_thread_locals:
            delattr(mock_thread_locals, "defered_replications")
            defer_replication(mock_target)

            assert mock_target.name in mock_thread_locals.defered_replications
            assert mock_thread_locals.defered_replications[mock_target.name][0] == mock_target

            clear_deferred_replications(mock_target.name)

            assert mock_target.name not in mock_thread_locals.defered_replications


def test_signals_register_device_account_not_created_or_raw(test_device, second_test_device):
    """
    Tests that if created or raw are set to True, the function returns before any code
    can be executed.
    """

    # patch the logger to verify that it was never called
    with patch(f"{FILE_PATH}.logger") as mock_logger:
        # created and raw both True
        register_device_account(
            sender=test_device, instance=second_test_device, created=False, raw=False
        )

        # both are True
        register_device_account(
            sender=test_device, instance=second_test_device, created=True, raw=True
        )

        # only created is False
        register_device_account(
            sender=test_device, instance=second_test_device, created=False, raw=True
        )

    mock_logger.info.assert_not_called()


@patch(
    "fractal.matrix.FractalAsyncClient.register_with_token",
)
@patch(
    "fractal_database_matrix.models.MatrixCredentials.objects.create",
)
@patch("fractal.cli.controllers.auth.AuthenticatedController")
def test_signals_register_device_account_with_creds(
    mock_auth_controller,
    mock_matrix_creds,
    mock_register,
    test_device,
    test_homeserver_url,
    test_user_access_token,
):
    """ """

    test_matrix_id = "@admin:localhost"
    mock_device = MagicMock(spec=Device)
    mock_device.name = "test_name"
    mock_device_id = f"@{mock_device.name}:localhost"
    mock_auth_controller.get_creds = MagicMock()
    mock_auth_controller.get_creds.return_value = [
        test_user_access_token,
        test_homeserver_url,
        test_matrix_id,
    ]
    mock_register.return_value = "test_access_token"

    register_device_account(sender=test_device, instance=mock_device, created=True, raw=False)

    call_args = mock_matrix_creds.call_args.kwargs
    assert "password" in call_args
    assert len(call_args["password"]) == 64
    assert call_args["matrix_id"] == mock_device_id
    assert call_args["access_token"] == "test_access_token"
    assert call_args["device"] == mock_device

def test_signals_register_device_account_no_creds(test_device):
    """
    """
    
    mock_device = MagicMock(spec=Device)
    mock_device.name = "test_name"

    with patch("fractal.cli.controllers.auth.AuthenticatedController") as mock_auth_controller:
        with patch("fractal_database.models.Database.current_db") as mock_current_db:
            with patch("fractal_database_matrix.models.MatrixCredentials.objects.create") as mock_create:
                with patch("fractal.matrix.FractalAsyncClient.register_with_token") as mock_register:
                    mock_register.return_value = "test_access_token"
                    mock_create.return_value = MagicMock()
                    mock_current_db.primary_target = MagicMock()
                    mock_auth_controller.get_creds = MagicMock(return_value=None)
                    assert mock_auth_controller.get_creds() is None
                    register_device_account(sender=test_device, instance=mock_device, created=True, raw=False)

    mock_create.assert_called_once()

def test_signals_increment_version(test_device, second_test_device):
    """ """

    original_version = test_device.object_version

    increment_version(sender=second_test_device, instance=test_device)

    assert test_device.object_version == original_version + 1


def test_signals_object_post_save_raw(test_device, second_test_device):
    """ """

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        result = object_post_save(
            sender=second_test_device,
            instance=test_device,
            created=False,
            raw=True,
        )

    assert result is None
    mock_logger.info.assert_called_with(f"Loading instance from fixture: {test_device}")


def test_signals_object_post_save_verify_second_call(test_device, second_test_device):
    """
    Tests that if the user is not in a transaction, it will enter one before making
    a recursive call to object_post_save
    """

    mock_no_connection = MagicMock()
    mock_no_connection.in_atomic_block = False

    mock_connection = MagicMock()
    mock_connection.in_atomic_block = True

    with patch(f"{FILE_PATH}.object_post_save") as mock_post_save:
        with patch(f"{FILE_PATH}.transaction") as mock_transaction:
            mock_transaction.get_connection.side_effect = [mock_no_connection, mock_connection]
            result = object_post_save(
                sender=second_test_device,
                instance=test_device,
                created=False,
                raw=False,
            )

    mock_post_save.assert_called_once()
    mock_transaction.atomic.assert_called_once()


def test_signals_object_post_save_in_nested_signal_handler(test_device, second_test_device):
    """ """

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        with patch(f"{FILE_PATH}.in_nested_signal_handler", return_value=True):
            result = object_post_save(
                sender=second_test_device,
                instance=test_device,
                created=False,
                raw=False,
            )

    assert result is None
    mock_logger.info.assert_called_with(f"Back inside post_save for instance: {test_device}")


def test_signals_object_post_save_not_in_nested_signal_handler(test_device, second_test_device):
    """ """
    test_device.schedule_replication = MagicMock()

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        with patch(f"{FILE_PATH}.in_nested_signal_handler", return_value=False):
            result = object_post_save(
                sender=second_test_device,
                instance=test_device,
                created=False,
                raw=False,
            )

    call_args_list = mock_logger.info.call_args_list
    args = []
    args.append(call_args_list[0][0])
    args.append(call_args_list[1][0])

    not_comparison_tuple = (f"Back inside post_save for instance: {test_device}",)
    comparison_tuple = (f"Outermost post save instance: {test_device}",)
    assert not_comparison_tuple not in args
    assert comparison_tuple in args
    test_device.schedule_replication.assert_called_once()


def test_signals_schedule_replication_on_m2m_change_invalid_action(
    test_device, second_test_device
):
    """
    #? action not in the given dictionary
    """

    sender = test_device
    instance = second_test_device

    with patch(f"{FILE_PATH}.print") as mock_print:
        result = schedule_replication_on_m2m_change(
            sender=sender,
            instance=instance,
            action="invalid_action_not_found_in_set",
            reverse=True,
            model=sender,
            pk_set=[],
        )

    assert result is None
    mock_print.assert_not_called()


def test_signals_schedule_replication_on_m2m_change_empty_pk_set(test_device, second_test_device):
    """
    #? pass pk as empty list
    """

    sender = test_device
    instance = second_test_device

    sender.save = MagicMock()
    sender.schedule_replication = MagicMock()

    with patch(f"{FILE_PATH}.logger.debug") as mock_print:
        result = schedule_replication_on_m2m_change(
            sender=sender,
            instance=instance,
            action="post_add",
            reverse=True,
            model=sender,
            pk_set=[],
        )

    # verify that you got passed the "action" check
    mock_print.assert_called_once()

    # verify that the for loop was a no-op
    sender.save.assert_not_called()
    sender.schedule_replication.assert_not_called()


def test_signals_schedule_replication_on_m2m_change_true_reverse(test_device, second_test_device):
    """
    #? set reverse to True
    """

    sender = test_device
    instance = second_test_device

    sender.schedule_replication = MagicMock()
    instance.schedule_replication = MagicMock()
    ids = [f"{sender.id}"]
    device_model = MagicMock(spec=Device)
    mock_object_get = MagicMock(return_value=sender)
    device_model.objects.get = mock_object_get

    result = schedule_replication_on_m2m_change(
        sender=sender,
        instance=instance,
        action="post_add",
        reverse=True,
        model=device_model,  # type: ignore
        pk_set=ids,
    )

    sender.schedule_replication.assert_called_once_with(created=False)
    instance.schedule_replication.assert_called_once_with(created=False)


def test_signals_schedule_replication_on_m2m_change_false_reverse(
    test_device, second_test_device
):
    """
    #? set reverse to false
    """

    sender = test_device
    instance = second_test_device

    instance.schedule_replication = MagicMock()
    sender.schedule_replication = MagicMock()
    instance.schedule_replication = MagicMock()
    ids = [f"{sender.id}"]
    device_model = MagicMock(spec=Device)
    mock_object_get = MagicMock(return_value=sender)
    device_model.objects.get = mock_object_get

    result = schedule_replication_on_m2m_change(
        sender=sender,
        instance=instance,
        action="post_add",
        reverse=False,
        model=device_model,  # type: ignore
        pk_set=ids,
    )

    instance.schedule_replication.assert_called_once()
    sender.schedule_replication.assert_not_called()


def test_signals_create_database_and_matrix_replication_target_verify_second_call():
    """ """

    mock_no_connection = MagicMock()
    mock_no_connection.in_atomic_block = False

    mock_connection = MagicMock()
    mock_connection.in_atomic_block = True

    with patch(f"{FILE_PATH}.transaction") as mock_transaction:
        with patch(
            f"{FILE_PATH}.create_database_and_matrix_replication_target"
        ) as mock_create_db:
            mock_transaction.get_connection.side_effect = [mock_no_connection, mock_connection]
            create_database_and_matrix_replication_target()

    mock_transaction.atomic.assert_called_once()
    mock_create_db.assert_called_once()


def test_signals_create_database_and_matrix_replication_target_verify_db_created():
    """
    #? happy path, figure out how to verify that the db was created
        #? its working right now, just need to verify
    """

    with pytest.raises(Database.DoesNotExist):
        Database.objects.get()

    create_database_and_matrix_replication_target()

    db = Database.objects.get()


def test_signals_create_database_and_matrix_replication_target_no_creds_no_os_environ():
    """
    #? patches in this test might be breaking subsequent tests
    """

    with patch(
        f"fractal.cli.controllers.auth.AuthenticatedController.get_creds", return_value=None
    ):
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "fractal_database_matrix.models.MatrixReplicationTarget.objects.get_or_create"
            ) as mock_get_or_create:
                create_database_and_matrix_replication_target()

    mock_get_or_create.assert_not_called()


def test_signals_create_database_and_matrix_replication_target_with_creds(
    logged_in_db_auth_controller,
):
    """ """

    creds = AuthenticatedController.get_creds()

    db_project_name = os.path.basename(settings.BASE_DIR)
    from fractal_database.signals import get_deferred_replications

    # if there are creds, os.environ will not be used
    create_database_and_matrix_replication_target()

    d = Database.objects.get(name=db_project_name)

    target = d.primary_target()

    assert isinstance(target, MatrixReplicationTarget)

    assert target.metadata["room_id"]

    targets = d.get_all_replication_targets()
    assert isinstance(targets[0], DummyReplicationTarget)
    assert len(targets) == 2

    device = d.devices.get()

    assert socket.gethostname().lower() in device.name


def test_signals_accept_invite_successful_join(
    test_matrix_creds, test_database, logged_in_db_auth_controller
):
    """
    Tests both invite and accept invite
    """

    room_id = test_database.primary_target().metadata["room_id"]
    homeserver = test_database.primary_target().homeserver
    creds = AuthenticatedController.get_creds()

    async def verify_pending_invite():
        async with MatrixClient(
            homeserver_url=homeserver,
            access_token=test_matrix_creds.access_token,
            matrix_id=test_matrix_creds.matrix_id,
        ) as client:
            res = await client.sync(since=None)
            return room_id in res.rooms.invite

    async def get_room_state():
        async with MatrixClient(
            homeserver_url=homeserver,
            access_token=test_matrix_creds.access_token,
            matrix_id=test_matrix_creds.matrix_id,
        ) as client:
            res = await client.room_get_state(room_id)
            return isinstance(res, RoomGetStateResponse)

    assert not async_to_sync(verify_pending_invite)()

    async_to_sync(_invite_device)(test_matrix_creds, room_id, homeserver)

    async_to_sync(_accept_invite)(test_matrix_creds, room_id, homeserver)
    assert async_to_sync(get_room_state)()


def test_signals_accept_invite_not_logged_in(test_matrix_creds, test_database):
    """
    Tests both invite and accept invite
    """

    room_id = test_database.primary_target().metadata["room_id"]
    homeserver = test_database.primary_target().homeserver

    async def verify_pending_invite():
        async with MatrixClient(
            homeserver_url=homeserver,
            access_token=test_matrix_creds.access_token,
            matrix_id=test_matrix_creds.matrix_id,
        ) as client:
            res = await client.sync(since=None)
            return room_id in res.rooms.invite

    async def get_room_state():
        async with MatrixClient(
            homeserver_url=homeserver,
            access_token=test_matrix_creds.access_token,
            matrix_id=test_matrix_creds.matrix_id,
        ) as client:
            res = await client.room_get_state(room_id)
            return isinstance(res, RoomGetStateResponse)

    assert not async_to_sync(verify_pending_invite)()

    # patch get_creds to return None, forcing it to use environment variables
    with patch(
        "fractal.cli.controllers.auth.AuthenticatedController.get_creds"
    ) as mock_get_creds:
        mock_get_creds.return_value = None
        async_to_sync(_invite_device)(test_matrix_creds, room_id, homeserver)

    async_to_sync(_accept_invite)(test_matrix_creds, room_id, homeserver)
    assert async_to_sync(get_room_state)()


def test_signals_join_device_to_database_not_post_add(test_database):
    """ """

    with patch("fractal_database.models.Device") as mock_device:
        result = join_device_to_database(test_database, test_database, [], action="not_post_add")

    mock_device.current_device.assert_not_called()
    assert result is None


def test_signals_join_device_to_database_empty_pk(test_database):
    """ """

    with patch("fractal_database.models.Device") as mock_device:
        result = join_device_to_database(test_database, test_database, [], action="post_add")

    mock_device.objects.get.assert_not_called()


def test_signals_join_device_to_database_device_id_equals_current_device_pk(test_database):
    """ """

    test_database.primary_target = MagicMock()
    device = Device.current_device()

    # pass the device pk, triggering the loop to continue
    result = join_device_to_database(test_database, test_database, [device.pk], action="post_add")

    test_database.primary_target.assert_not_called()


def test_signals_join_device_to_database_follow_through_with_invite(test_database, test_device):
    """ """

    primary_target = test_database.primary_target()
    pk = primary_target.pk

    device = test_device
    pk_list = [device.pk]

    test_database.primary_target = MagicMock(return_value=primary_target)

    # pass the pk of the primary target in the list, triggering the loop to continue
    result = join_device_to_database(test_database, test_database, pk_list, action="post_add")

    test_database.primary_target.assert_called()


async def test_signals_lock_and_put_state_no_creds():
    """ """

    test_repr = Representation()
    mock_repl_target = MagicMock(spec=DummyReplicationTarget)

    with patch(
        "fractal.cli.controllers.auth.AuthenticatedController.get_creds"
    ) as mock_get_creds:
        mock_get_creds.return_value = None
        with pytest.raises(Exception) as e:
            await _lock_and_put_state(
                test_repr, "test_room_id", mock_repl_target, "test_state_type", {}
            )

    assert str(e.value) == "No creds found not locking and putting state"


async def test_signals_lock_and_put_state_with_creds(logged_in_db_auth_controller, test_room_id):
    """ """

    assert AuthenticatedController.get_creds() is not None

    test_repr = Representation()
    mock_repl_target = MagicMock(spec=DummyReplicationTarget)
    test_repr.put_state = AsyncMock()
    test_dict = {"test": "dict"}
    test_type = "test_state_type"

    await _lock_and_put_state(test_repr, test_room_id, mock_repl_target, test_type, test_dict)

    test_repr.put_state.assert_called_with(test_room_id, mock_repl_target, test_type, test_dict)


async def test_signals_lock_and_put_state_lock_error(logged_in_db_auth_controller, test_room_id):
    """ """

    assert AuthenticatedController.get_creds() is not None

    test_repr = Representation()
    mock_repl_target = MagicMock(spec=DummyReplicationTarget)
    test_repr.put_state = AsyncMock()
    test_dict = {"test": "dict"}
    test_type = "test_state_type"

    with patch(f"{FILE_PATH}.MatrixLock.lock", side_effect=LockAcquireError("test message")):
        with pytest.raises(LockAcquireError) as e:
            await _lock_and_put_state(
                test_repr, test_room_id, mock_repl_target, test_type, test_dict
            )

    assert str(e.value) == "test message"


def test_signals_update_target_state_no_update_incorrect_model_type():
    """ """

    not_db_or_repl_target_instance = NotDatabaseOrReplTarget()
    instance = MagicMock(spec=DummyReplicationTarget)

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        update_target_state(
            not_db_or_repl_target_instance,  # type: ignore
            not_db_or_repl_target_instance,  # type: ignore
            created=False,
            raw=False,
        )

    mock_logger.info.assert_not_called()


def test_signals_update_target_state_no_update_created_or_raw():
    """ """

    instance = MagicMock(spec=MatrixReplicationTarget)

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        # created True
        update_target_state(
            instance,
            instance,
            created=True,
            raw=False,
        )

        # raw True
        update_target_state(
            instance,
            instance,
            created=False,
            raw=True,
        )

        # both True
        update_target_state(
            instance,
            instance,
            created=True,
            raw=True,
        )

    mock_logger.info.assert_not_called()


def test_signals_update_target_state_no_update_not_primary():
    """ """

    instance = MagicMock(spec=MatrixReplicationTarget)
    instance.primary = False
    instance.metadata.get = MagicMock()

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        update_target_state(
            instance,
            instance,
            created=False,
            raw=False,
        )

    # if logger.info is called and instance.metadata.get is not called, there is only
    # once case it could be
    mock_logger.info.assert_not_called()
    instance.metadata.get.assert_not_called()


def test_signals_update_target_state_no_update_db_primary_target_not_replication_target():
    """ """

    instance = MagicMock(spec=Database)
    instance.primary_target = MagicMock()

    target = MagicMock(spec=NotDatabaseOrReplTarget)
    target.metadata = MagicMock()
    target.metadata.get = MagicMock()
    instance.primary_target.return_value = target

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        update_target_state(
            instance,
            instance,
            created=False,
            raw=False,
        )

    mock_logger.warning.assert_called_once()
    target.metadata.get.assert_not_called()


def test_signals_update_target_state_no_update_no_room_id():
    """ """

    instance = MagicMock(spec=MatrixReplicationTarget)
    instance.primary = True
    instance.metadata = MagicMock()
    instance.metadata.get = MagicMock(return_value=None)

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        update_target_state(
            instance,
            instance,
            created=False,
            raw=False,
        )

    instance.metadata.get.assert_called_once()
    mock_logger.warning.assert_called_once()


def test_signals_update_target_state_target_update():
    """
    line 475
    """

    instance = MagicMock(spec=MatrixReplicationTarget)
    instance.primary = True

    instance.to_fixture = MagicMock()
    instance.to_fixture.return_value = {}

    instance.get_representation_module = MagicMock()
    instance.get_representation_module.return_value = "test_return_value"

    instance.metadata = MagicMock()
    instance.metadata.get = MagicMock(return_value="test_room_id")
    mock_repr_instance = MagicMock(spec=Representation)

    expected_type = "f.database.target"

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        with patch(
            "fractal_database.models.RepresentationLog._get_repr_instance",
            new=MagicMock(return_value=mock_repr_instance),
        ):
            with patch(f"{FILE_PATH}._lock_and_put_state") as mock_lock_and_put_state:
                update_target_state(
                    instance,
                    instance,
                    created=False,
                    raw=False,
                )

    mock_lock_and_put_state.assert_called_with(
        mock_repr_instance, "test_room_id", instance, expected_type, {"fixture": {}}
    )


def test_signals_update_target_state_db_update():
    """
    line 475
    """

    instance = MagicMock(spec=Database)
    primary_target = MagicMock(spec=MatrixReplicationTarget)
    instance.primary_target = MagicMock(return_value=primary_target)

    instance.to_fixture = MagicMock()
    instance.to_fixture.return_value = {}

    primary_target.get_representation_module = MagicMock()
    primary_target.get_representation_module.return_value = "test_return_value"

    primary_target.metadata = MagicMock()
    primary_target.metadata.get = MagicMock(return_value="test_room_id")
    mock_repr_instance = MagicMock(spec=Representation)

    expected_type = "f.database"

    with patch(
        "fractal_database.models.RepresentationLog._get_repr_instance",
        new=MagicMock(return_value=mock_repr_instance),
    ):
        with patch(f"{FILE_PATH}._lock_and_put_state") as mock_lock_and_put_state:
            update_target_state(
                instance,
                instance,
                created=False,
                raw=False,
            )

    mock_lock_and_put_state.assert_called_with(
        mock_repr_instance, "test_room_id", primary_target, expected_type, {"fixture": {}}
    )


def test_signals_zip_django_app_():
    """ """

    app1 = "app1"
    test_dir = FRACTAL_EXPORT_DIR

    os.makedirs(f"{test_dir}/{app1}", exist_ok=True)
    os.makedirs(f"{test_dir}/extracted", exist_ok=True)
    with open(f"{test_dir}/{app1}/xyz.py", "w"):
        pass

    mock_app_config = MagicMock(spec=AppConfig)

    mock_app_config.path = f"{test_dir}/{app1}"
    mock_app_config.name = "test_name"

    zip_django_app(mock_app_config)

    assert os.path.exists(f"{test_dir}/{mock_app_config.name}.tar.gz")

    with tarfile.open(f"{test_dir}/{mock_app_config.name}.tar.gz", "r:gz") as tar:
        result = tar.extractall(f"{test_dir}/extracted")

    all_files = []
    for root, dirs, files in os.walk(f"{test_dir}/extracted"):
        all_files.extend(files)

    assert "pyproject.toml" in all_files
    assert "xyz.py" in all_files


def test_signals_zip_django_app_empty_app_dir():
    """ """
    app1 = "app1"
    test_dir = FRACTAL_EXPORT_DIR

    os.makedirs(f"{test_dir}/{app1}", exist_ok=True)
    os.makedirs(f"{test_dir}/extracted", exist_ok=True)

    mock_app_config = MagicMock(spec=AppConfig)

    mock_app_config.path = f"{test_dir}/{app1}"
    mock_app_config.name = "test_name"

    assert not os.path.exists(f"{mock_app_config.path}/pyproject.toml")
    with patch(f"{FILE_PATH}.tarfile.TarFile.add") as mock_tar_add:
        zip_django_app(mock_app_config)

    mock_tar_add.assert_not_called()
    assert os.path.exists(f"{test_dir}/{mock_app_config.name}.tar.gz")

    with tarfile.open(f"{test_dir}/{mock_app_config.name}.tar.gz", "r:gz") as tar:
        result = tar.extractall(f"{test_dir}/extracted")

    all_files = []
    for root, dirs, files in os.walk(f"{test_dir}/extracted"):
        all_files.extend(files)

    assert os.path.exists(f"{test_dir}/extracted/pyproject.toml")
    assert len(files) == 1


def test_signals_zip_django_app_existing_pyproject():
    """ """

    app1 = "app1"
    test_dir = FRACTAL_EXPORT_DIR

    os.makedirs(f"{test_dir}/{app1}", exist_ok=True)
    os.makedirs(f"{test_dir}/extracted", exist_ok=True)
    with open(f"{test_dir}/{app1}/pyproject.toml", "w"):
        pass
    with open(f"{test_dir}/{app1}/xyz.py", "w"):
        pass

    mock_app_config = MagicMock(spec=AppConfig)

    mock_app_config.path = f"{test_dir}/{app1}"
    mock_app_config.name = "test_name"

    with patch(f"{FILE_PATH}.init_poetry_project") as mock_init_poetry_project:
        zip_django_app(mock_app_config)

    assert os.path.exists(f"{test_dir}/{mock_app_config.name}.tar.gz")

    with tarfile.open(f"{test_dir}/{mock_app_config.name}.tar.gz", "r:gz") as tar:
        result = tar.extractall(f"{test_dir}/extracted")

    all_files = []
    for root, dirs, files in os.walk(f"{test_dir}/extracted"):
        all_files.extend(files)

    mock_init_poetry_project.assert_not_called()

    assert "pyproject.toml" in all_files
    assert "xyz.py" in all_files


async def test_signals_upload_app_wrong_file_type():
    """ """

    mock_primary_target = MagicMock(spec=MatrixReplicationTarget)
    mock_primary_target.aget_creds = AsyncMock()

    wrong_file_type = "test.txt"
    room_id = "test_room_id"

    mock_repr_instance = MagicMock(spec=Representation)

    await _upload_app(
        room_id=room_id,
        app=wrong_file_type,
        repr_instance=mock_repr_instance,
        primary_target=mock_primary_target,
    )

    mock_primary_target.aget_creds.assert_not_called()


async def test_signals_upload_app_functional_test(test_database):
    """ """

    primary_target = await sync_to_async(test_database.primary_target)()
    room_id = primary_target.metadata["room_id"]
    file = "test.tar.gz"
    mock_repr = MagicMock(spec=Representation)
    upload_return = secrets.token_hex(8)

    with patch("fractal.matrix.FractalAsyncClient.upload_file") as mock_upload_file:
        with patch(f"{FILE_PATH}._lock_and_put_state") as mock_lock_and_put:
            mock_upload_file.return_value = upload_return
            await _upload_app(room_id, file, mock_repr, primary_target)

    mock_upload_file.assert_called_once()
    mock_lock_and_put.assert_called_once_with(
        mock_repr,  # type:ignore
        room_id,
        primary_target,
        f"f.database.app.test",
        {"mxc": upload_return},
    )


def test_signals_upload_exported_apps_filenotfound():
    """ """
    with patch(f"{FILE_PATH}.logger") as mock_logger:
        with patch(f"{FILE_PATH}.os.listdir", side_effect=FileNotFoundError()) as mock_listdir:
            upload_exported_apps()

    mock_logger.info.assert_called_with("No apps found in export directory. Skipping upload")


def test_signals_upload_exported_apps_db_doesnotexist():
    """ """

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        with patch(f"{FILE_PATH}.os") as mock_os:
            mock_os.listdir = MagicMock(return_value=True)
            upload_exported_apps()

    mock_logger.warning.assert_called_with("No current database found, skipping app upload")


def test_signals_upload_exported_apps_no_primary_target(test_database):
    """ """
    with patch(f"{FILE_PATH}.logger") as mock_logger:
        with patch(f"{FILE_PATH}.os") as mock_os:
            mock_os.listdir = MagicMock(return_value=True)
            with patch("fractal_database.models.Database.primary_target") as mock_primary_target:
                mock_primary_target.return_value = None
                upload_exported_apps()

    mock_logger.warning.assert_called_with("No primary target found, skipping app upload")


def test_signals_upload_exported_apps_primary_target_wrong_type(test_database):
    """ """

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        with patch(f"{FILE_PATH}.os") as mock_os:
            mock_os.listdir = MagicMock(return_value=True)
            with patch("fractal_database.models.Database.primary_target") as mock_primary_target:
                mock_primary_target.return_value = NotDatabaseOrReplTarget()
                assert mock_primary_target.return_value
                upload_exported_apps()

    mock_logger.warning.assert_called_with("No primary target found, skipping app upload")


def test_signals_upload_exported_apps_no_tar_gz(test_database, test_device):
    """ """

    app1 = "app1"
    app2 = "app2"
    app3 = "app3"

    os.mkdir(FRACTAL_EXPORT_DIR)
    os.mkdir(f"{FRACTAL_EXPORT_DIR}/{app1}")
    os.mkdir(f"{FRACTAL_EXPORT_DIR}/{app2}")
    os.mkdir(f"{FRACTAL_EXPORT_DIR}/{app3}")
    primary_target = test_database.primary_target()

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        with patch(f"{FILE_PATH}.async_to_sync") as mock_sync:
            upload_exported_apps()

    mock_sync.assert_not_called()
    mock_logger.info.assert_not_called()


def test_signals_upload_exported_apps_tar_gz(test_database, test_device):
    """ """

    app1 = "app1.tar.gz"
    app2 = "app2.tar.gz"
    app3 = "app3.tar.gz"

    os.mkdir(FRACTAL_EXPORT_DIR)

    with open(f"{FRACTAL_EXPORT_DIR}/{app1}", "w") as f:
        pass
    with open(f"{FRACTAL_EXPORT_DIR}/{app2}", "w") as f:
        pass
    with open(f"{FRACTAL_EXPORT_DIR}/{app3}", "w") as f:
        pass

    primary_target = test_database.primary_target()

    with patch(f"{FILE_PATH}._upload_app") as mock_upload:
        upload_exported_apps()

    assert mock_upload.call_count == 3


