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
    clear_deferred_replications,
    commit,
    create_database_and_matrix_replication_target,
    defer_replication,
    enter_signal_handler,
    get_deferred_replications,
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
    Tests that if there is an error replicating the target, it is logged and
    clear_deferred_replications is still called.
    """

    # create a mock target and give it a name
    mock_target = MagicMock(spec=DummyReplicationTarget)
    mock_target.name = "test_name"
    mock_target.replicate = AsyncMock()

    # set its replicate function to raise an exception
    mock_target.replicate.side_effect = Exception()

    # patch the logger and clear_deferred_replications
    with patch(f"{FILE_PATH}.logger", new=MagicMock()) as mock_logger:
        with patch(f"{FILE_PATH}.clear_deferred_replications", new=MagicMock()) as mock_clear:
            # call the function
            commit(mock_target)

    # verify that clear_deferred_replications and the logger are both called
    mock_clear.assert_called_with(mock_target.name)
    mock_logger.error.assert_called()


def test_signals_commit_no_error():
    """
    Tests that if there is no error replicating the target, the logger is not called and
    clear_deferred_replications is called.
    """

    # create a Replication target object
    repl_target = DummyReplicationTarget()
    repl_target.name = "test_name"

    # patch the logger and clear_deferred_replications
    with patch(f"{FILE_PATH}.logger", new=MagicMock()) as mock_logger:
        with patch(f"{FILE_PATH}.clear_deferred_replications", new=MagicMock()) as mock_clear:
            # call the function
            commit(repl_target)

    # verify that the logger is not called and that clear_deferred_replications is called
    mock_clear.assert_called_with(repl_target.name)
    mock_logger.error.assert_not_called()


def test_signals_defer_replication_not_in_transaction():
    """
    Tests that an exception is raised if you are not in a transaction when defer_replication
    is called.
    """

    # make a mock target object
    mock_target = MagicMock(spec=DummyReplicationTarget)
    mock_target.name = "test_name"

    # patch transaction and have it evaluate to false when determining if it is in a transaction
    with patch(f"{FILE_PATH}.transaction", new=MagicMock()) as mock_transaction:
        mock_transaction.get_connection = MagicMock()
        mock_transaction.get_connection.return_value = MagicMock()
        mock_transaction.get_connection.return_value.in_atomic_block = False
        # call the function to raise an exception
        with pytest.raises(Exception):
            defer_replication(mock_target)


def test_signals_defer_replication_no_defered_replications():
    """
    Tests that the function still executes when _thread_locals doesn't have a defered_replications
    attribute and one is created for it.
    """

    # create a mock target object
    mock_target = MagicMock(spec=DummyReplicationTarget)
    mock_target.name = "test_name"

    # patch the transaction to evaluate to True
    with patch(f"{FILE_PATH}.transaction", new=MagicMock()) as mock_transaction:
        mock_transaction.get_connection = MagicMock()
        mock_transaction.get_connection.return_value = MagicMock()
        mock_transaction.get_connection.return_value.in_atomic_block = True

        # patch _thread_locals and the logger
        with patch(f"{FILE_PATH}._thread_locals") as mock_thread_locals:
            # delete the defered_replications attribute from the logger
            delattr(mock_thread_locals, "defered_replications")
            assert get_deferred_replications() == {}

            # call the function
            defer_replication(mock_target)

    # verify on_commit was called
    mock_transaction.on_commit.assert_called_once()

    # verify that the target's name is in the defered_replications dictionary
    assert "test_name" in mock_thread_locals.defered_replications
    assert mock_thread_locals.defered_replications["test_name"][0] == mock_target


def test_signals_defer_replication_target_in_defered_replications():
    """
    Tests the case where the target is in the defered replication dictionary of
    _thread_local
    """

    # make a mock target object and generate a name for it
    mock_target = MagicMock(spec=DummyReplicationTarget)
    mock_target.name = secrets.token_hex(8)

    # patch the transaction and have it evaluate to True
    with patch(f"{FILE_PATH}.transaction", new=MagicMock()) as mock_transaction:
        mock_transaction.get_connection = MagicMock()
        mock_transaction.get_connection.return_value = MagicMock()
        mock_transaction.get_connection.return_value.in_atomic_block = True

        # patch the _thread_locals and the logger
        with patch(f"{FILE_PATH}._thread_locals") as mock_thread_locals:
            # set the defered_replications dictionary to include the target
            mock_thread_locals.defered_replications = {mock_target.name: [mock_target]}
            defer_replication(mock_target)

    # verify that on_commit was not called
    mock_transaction.on_commit.assert_not_called()

    # verify that the target is in defered_replications
    assert mock_target.name in mock_thread_locals.defered_replications
    assert mock_thread_locals.defered_replications[mock_target.name][0] == mock_target

    # accessing index 1 to verify that defer_replication adds the given target to the list
    assert mock_thread_locals.defered_replications[mock_target.name][1] == mock_target


def test_signals_clear_defered_replications_functional_test():
    """
    Tests that clear deferred replications removes the target from the defered replications
    dictionary.
    """

    # make a mock target object and generate a name for it
    mock_target = MagicMock(spec=DummyReplicationTarget)
    mock_target.name = secrets.token_hex(8)

    # patch the transaction and have it evaluate to True
    with patch(f"{FILE_PATH}.transaction", new=MagicMock()) as mock_transaction:
        mock_transaction.get_connection = MagicMock()
        mock_transaction.get_connection.return_value = MagicMock()
        mock_transaction.get_connection.return_value.in_atomic_block = True

        # patch _thread_locals
        with patch(f"{FILE_PATH}._thread_locals") as mock_thread_locals:
            # delete the defered_replications dictionary
            delattr(mock_thread_locals, "defered_replications")

            # call defer_replication
            defer_replication(mock_target)

            # verify that the target is in the dictionary
            assert mock_target.name in mock_thread_locals.defered_replications
            assert mock_thread_locals.defered_replications[mock_target.name][0] == mock_target

            # call clear_deferred_replications
            clear_deferred_replications(mock_target.name)

            # verify that the target is NOT in the defered_replications dictionary
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

    # verify that the logger is never called
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
    """
    Tests that if the user is logged in, credentials are used instead of the environment
    variables
    """

    # make a matrix id
    test_matrix_id = "@admin:localhost"

    # create a mock device object
    mock_device = MagicMock(spec=Device)
    mock_device.name = "test_name"
    mock_device_id = f"@{mock_device.name}:localhost"

    # create a mock auth controller to simulate a logged in user
    mock_auth_controller.get_creds = MagicMock()

    # assign credential values
    mock_auth_controller.get_creds.return_value = [
        test_user_access_token,
        test_homeserver_url,
        test_matrix_id,
    ]
    mock_register.return_value = "test_access_token"

    # call the function
    register_device_account(sender=test_device, instance=mock_device, created=True, raw=False)

    # verify that the values returned by creds are used to register with token
    call_args = mock_matrix_creds.call_args.kwargs
    assert "password" in call_args
    assert len(call_args["password"]) == 64
    assert call_args["matrix_id"] == mock_device_id
    assert call_args["access_token"] == "test_access_token"
    assert call_args["device"] == mock_device


def test_signals_register_device_account_no_creds(test_device):
    """
    Tests that environment variables are used when no creds are available, allowing
    the function to continue in registering the device
    """

    # make a mock device object
    mock_device = MagicMock(spec=Device)
    mock_device.name = "test_name"

    # patch the auth controller, current_db function, matrix creds create function, and register_with_token
    with patch("fractal.cli.controllers.auth.AuthenticatedController") as mock_auth_controller:
        with patch("fractal_database.models.Database.current_db") as mock_current_db:
            with patch(
                "fractal_database_matrix.models.MatrixCredentials.objects.create"
            ) as mock_create:
                with patch(
                    "fractal.matrix.FractalAsyncClient.register_with_token"
                ) as mock_register:
                    mock_register.return_value = "test_access_token"
                    mock_create.return_value = MagicMock()
                    mock_current_db.primary_target = MagicMock()
                    mock_auth_controller.get_creds = MagicMock(return_value=None)

                    # verify that th get_creds returns no usable creds
                    assert mock_auth_controller.get_creds() is None
                    register_device_account(
                        sender=test_device, instance=mock_device, created=True, raw=False
                    )

    # verify that the matrix creds object is still created
    mock_create.assert_called_once()


def test_signals_increment_version(test_device, second_test_device):
    """
    Tests that increment_version properly increments the objects version attribute
    """

    # store the original version attribute
    original_version = test_device.object_version

    # call increment_version
    increment_version(sender=second_test_device, instance=test_device)

    # verify that the new object_version is 1 greater than it was before
    assert test_device.object_version == original_version + 1


def test_signals_object_post_save_raw(test_device, second_test_device):
    """
    Tests that the function returns before doing anything if raw is passed as True
    """

    # patch the logger
    with patch(f"{FILE_PATH}.logger") as mock_logger:
        # call object_post_save
        result = object_post_save(
            sender=second_test_device,
            instance=test_device,
            created=False,
            raw=True,
        )

    # verify that None is returned
    assert result is None

    # verify that the logger is called
    mock_logger.info.assert_called_with(f"Loading instance from fixture: {test_device}")


def test_signals_object_post_save_verify_second_call(test_device, second_test_device):
    """
    Tests that if the user is not in a transaction, it will enter one before making
    a second call to object_post_save
    """

    # create mock connections, one that is False, and one that is True
    mock_no_connection = MagicMock()
    mock_no_connection.in_atomic_block = False

    mock_connection = MagicMock()
    mock_connection.in_atomic_block = True

    # patch objcet_post_save and the transaction
    with patch(f"{FILE_PATH}.object_post_save") as mock_post_save:
        with patch(f"{FILE_PATH}.transaction") as mock_transaction:
            # have the transaction evaluate to False the first time and True the second time
            mock_transaction.get_connection.side_effect = [mock_no_connection, mock_connection]

            # call object_post_save
            result = object_post_save(
                sender=second_test_device,
                instance=test_device,
                created=False,
                raw=False,
            )

    # verify that object_post_save was called once from within the fuinction
    mock_post_save.assert_called_once()

    # verify that atomic was called only once
    mock_transaction.atomic.assert_called_once()


def test_signals_object_post_save_in_nested_signal_handler(test_device, second_test_device):
    """
    Tests that None is returned before scheduling replication if you are already
    in a nested signal handler
    """

    # mock the device's schedule_replication function
    test_device.schedule_replication = MagicMock()

    # patch in_nested_signal_handler and exit_signal_handler
    with patch(f"{FILE_PATH}.in_nested_signal_handler", return_value=True):
        # call the function
        result = object_post_save(
            sender=second_test_device,
            instance=test_device,
            created=False,
            raw=False,
        )

    # verify that the function returned None and that the expected logger call was made
        # NOTE: There is only one case where None is returned when "raw" is False
    assert result is None
    
    # verify that schedule_replication was not called
    test_device.schedule_replication.assert_not_called()


def test_signals_object_post_save_not_in_nested_signal_handler(test_device, second_test_device):
    """
    Tests that the function does not return before scheduling replication if you are
    not in a nested signal handler
    """

    # mock the device's schedule_replication function
    test_device.schedule_replication = MagicMock()

    # patch in_nested_signal_handler
    with patch(f"{FILE_PATH}.in_nested_signal_handler", return_value=False):
        # call the function
        result = object_post_save(
            sender=second_test_device,
            instance=test_device,
            created=False,
            raw=False,
        )

    # verify that schedule_replication was called
    test_device.schedule_replication.assert_called_once()


def test_signals_schedule_replication_on_m2m_change_invalid_action(
    test_device, second_test_device
):
    """
    Tests that the function retruns before scheduling a replication if the action passed
    is not one of the valid actions that is expected by the function
    """

    # establish a sender and instance
    sender = test_device
    instance = second_test_device

    # patch the print function
    with patch(f"{FILE_PATH}.logger") as mock_logger:
        # call the function passing an invalid action
        result = schedule_replication_on_m2m_change(
            sender=sender,
            instance=instance,
            action="invalid_action_not_found_in_set",
            reverse=True,
            model=sender,
            pk_set=[],
        )

    # verify that None is returned by the function
    assert result is None

    # verify that print was never called
    mock_logger.debug.assert_not_called()


def test_signals_schedule_replication_on_m2m_change_empty_pk_set(test_device, second_test_device):
    """
    Tests that the loop iterating through pks is a no-op if the list is empty
    """

    # establish a sender and instance device
    sender = test_device
    instance = second_test_device

    # mock the instance's schedule_replication function
    instance.schedule_replication = MagicMock()

    # call the function passing an empty pk set
    result = schedule_replication_on_m2m_change(
        sender=sender,
        instance=instance,
        action="post_add",
        reverse=True,
        model=sender,
        pk_set=[],
    )


    # verify that the for loop was a no-op
        # NOTE: The instance's schedule_replication is called in both the "if" and the
        # "else" block of the for loop. If neither are called, then the for loop did
        # not execute.
    instance.schedule_replication.assert_not_called()


def test_signals_schedule_replication_on_m2m_change_pk_set_not_empty(test_device, second_test_device):
    """
    Tests that a related instance is fetched and has a replication scheduled if reverse
    is passed as True
    """

    # establish a sender and instance
    sender = test_device
    instance = second_test_device

    # mock the schedule_replication functions of the sender and instance
    sender.schedule_replication = MagicMock()
    instance.schedule_replication = MagicMock()

    # create a list containing the sender's id
    ids = [f"{sender.id}"]

    # create a mock device and mock the objects.get functions
    device_model = MagicMock(spec=Device)
    mock_object_get = MagicMock(return_value=sender)
    device_model.objects.get = mock_object_get

    # call the function passing the list containing the id
    result = schedule_replication_on_m2m_change(
        sender=sender,
        instance=instance,
        action="post_add",
        reverse=True,
        model=device_model,  # type: ignore
        pk_set=ids,
    )

    # verify that both schedule replications are called
    sender.schedule_replication.assert_called_once_with(created=False)
    instance.schedule_replication.assert_called_once_with(created=False)


def test_signals_create_database_and_matrix_replication_target_verify_second_call():
    """
    Tests that if you are not in a transaction, you enter a transaction and
    create_database_and_matrix_replication_target is called again from within a transaction
    """

    # create mock connection objects that result in a False and True connection status
    mock_no_connection = MagicMock()
    mock_no_connection.in_atomic_block = False

    mock_connection = MagicMock()
    mock_connection.in_atomic_block = True

    # patch the transaction class
    with patch(f"{FILE_PATH}.transaction") as mock_transaction:
        # patch the function
        with patch(
            f"{FILE_PATH}.create_database_and_matrix_replication_target"
        ) as mock_create_db:
            # set the connection to be False first, then True the second time
            mock_transaction.get_connection.side_effect = [mock_no_connection, mock_connection]

            # call the function
            create_database_and_matrix_replication_target()

    # verify that transaction.atomic was only called once
    mock_transaction.atomic.assert_called_once()

    # verify that create_database_and_matrix_replication_target is only called once
    mock_create_db.assert_called_once()


def test_signals_create_database_and_matrix_replication_target_verify_db_created():
    """
    Tests that a database is created when no errors occur
    """

    # attempt to fetch the database without creating it
    with pytest.raises(Database.DoesNotExist):
        Database.objects.get()

    # call the function
    create_database_and_matrix_replication_target()

    # fetch the database without raising an error
    db = Database.objects.get()


def test_signals_create_database_and_matrix_replication_target_no_creds():
    """
    Tests that if the user is logged in, a warning is issued and the function returns
    before creating a replication target
    """

    # patch get creds to return None
    with patch(
        f"fractal.cli.controllers.auth.AuthenticatedController.get_creds", return_value=None
    ):
        # patch get_or_create
        with patch(
            "fractal_database_matrix.models.MatrixReplicationTarget.objects.get_or_create"
        ) as mock_get_or_create:
            # call the function
            create_database_and_matrix_replication_target()

    # verify that get_or_create is never called
    mock_get_or_create.assert_not_called()


def test_signals_create_database_and_matrix_replication_target_with_creds(
    logged_in_db_auth_controller,
):
    """
    Tests that the replication target is created when the user is logged in
    """

    # get creds from the logged in user
    creds = AuthenticatedController.get_creds()

    # save the project name
    db_project_name = os.path.basename(settings.BASE_DIR)
    from fractal_database.signals import get_deferred_replications

    # call the function
    create_database_and_matrix_replication_target()

    # fetch the database using the project name
    d = Database.objects.get(name=db_project_name)

    # store the database primary target
    target = d.primary_target()

    # verify that the target is a MatrixReplicationTarget object
    assert isinstance(target, MatrixReplicationTarget)

    # verify the target's room id
    assert target.metadata["room_id"]

    # verify that target's replication targets
    targets = d.get_all_replication_targets()
    assert isinstance(targets[0], DummyReplicationTarget)
    assert len(targets) == 2

    # get the device
    device = d.devices.get()

    # verify that the device's name is the same as the sockets host name
    assert socket.gethostname().lower() in device.name


def test_signals_accept_invite_successful_join(
    test_matrix_creds, test_database, logged_in_db_auth_controller
):
    """
    Tests the case of a successful invite and join by a device
    """

    # store the room id and homeserver of the databases primary target
    room_id = test_database.primary_target().metadata["room_id"]
    homeserver = test_database.primary_target().homeserver
    creds = AuthenticatedController.get_creds()

    # function for verifying the pending invite
    async def verify_pending_invite():
        async with MatrixClient(
            homeserver_url=homeserver,
            access_token=test_matrix_creds.access_token,
            matrix_id=test_matrix_creds.matrix_id,
        ) as client:
            res = await client.sync(since=None)
            return room_id in res.rooms.invite # type: ignore

    # function for getting the room state
    async def get_room_state():
        async with MatrixClient(
            homeserver_url=homeserver,
            access_token=test_matrix_creds.access_token,
            matrix_id=test_matrix_creds.matrix_id,
        ) as client:
            res = await client.room_get_state(room_id)
            return isinstance(res, RoomGetStateResponse)

    # verify that there is no pending invite
    assert not async_to_sync(verify_pending_invite)()

    # invite the device
    async_to_sync(_invite_device)(test_matrix_creds, room_id, homeserver)

    # accept the invite
    async_to_sync(_accept_invite)(test_matrix_creds, room_id, homeserver)

    # verify that the room state is a RoomGetStateResponse
    assert async_to_sync(get_room_state)()


def test_signals_accept_invite_not_logged_in(test_matrix_creds, test_database):
    """
    Tests that a device can still be invited when the user is not logged in.
    """

    # get the room id and homeserver from the database's primary target
    room_id = test_database.primary_target().metadata["room_id"]
    homeserver = test_database.primary_target().homeserver

    # function for verifying the pending invite
    async def verify_pending_invite():
        async with MatrixClient(
            homeserver_url=homeserver,
            access_token=test_matrix_creds.access_token,
            matrix_id=test_matrix_creds.matrix_id,
        ) as client:
            res = await client.sync(since=None)
            return room_id in res.rooms.invite # type: ignore

    # function for getting the room state
    async def get_room_state():
        async with MatrixClient(
            homeserver_url=homeserver,
            access_token=test_matrix_creds.access_token,
            matrix_id=test_matrix_creds.matrix_id,
        ) as client:
            res = await client.room_get_state(room_id)
            return isinstance(res, RoomGetStateResponse)

    # verify that there is no pending invite
    assert not async_to_sync(verify_pending_invite)()

    # patch get_creds to return None, forcing it to use environment variables
    with patch(
        "fractal.cli.controllers.auth.AuthenticatedController.get_creds"
    ) as mock_get_creds:
        mock_get_creds.return_value = None
        async_to_sync(_invite_device)(test_matrix_creds, room_id, homeserver)

    # accept the invite
    async_to_sync(_accept_invite)(test_matrix_creds, room_id, homeserver)

    # verify that the room state is a RoomGetStateResponse
    assert async_to_sync(get_room_state)()


def test_signals_join_device_to_database_not_post_add(test_database):
    """
    Tests that the function returns before any actions are taken if "post_add" is not
    in the kwargs dictionary
    """

    # patch the device class
    with patch("fractal_database.models.Device") as mock_device:
        # call the function
        result = join_device_to_database(test_database, test_database, [], action="not_post_add")

    # verify that Device.current_device is not called
    mock_device.current_device.assert_not_called()

    # verify that the function returns None
    assert result is None


def test_signals_join_device_to_database_empty_pk(test_database):
    """
    Tests that the pk_set loop is a no-op if the pk list is empty
    """

    # patch the Device class
    with patch("fractal_database.models.Device") as mock_device:
        # call the function passing an empty pk list
        result = join_device_to_database(test_database, test_database, [], action="post_add")

    # verify that Device.objects.get is not called
    mock_device.objects.get.assert_not_called()


def test_signals_join_device_to_database_device_id_equals_current_device_pk(test_database):
    """
    Tests that the function continues and does not send out any invites if the
    device id is equal to the current_device pk
    """

    # mock the primary_target function of the database
    test_database.primary_target = MagicMock()

    # get the current device
    device = Device.current_device()

    # pass the device pk, triggering the loop to continue
    result = join_device_to_database(test_database, test_database, [device.pk], action="post_add")

    # verify that primary target is never called, meaning the loop continued before sending invites
    test_database.primary_target.assert_not_called()


def test_signals_join_device_to_database_follow_through_with_invite(test_database, test_device):
    """
    Tests the functionality of the device invites within the function
    """

    # set a primary target from the database
    primary_target = test_database.primary_target()

    # store the primary key of the primary target
    pk = primary_target.pk

    # store the device primary key in a list
    device = test_device
    pk_list = [device.pk]

    # mock the primary_target function of the database and have it return the primary target
    # this is done for function call verification purposes
    test_database.primary_target = MagicMock(return_value=primary_target)

    # pass the pk of the primary target in the list
    result = join_device_to_database(test_database, test_database, pk_list, action="post_add")

    # verify that primary target was called
    test_database.primary_target.assert_called()


async def test_signals_lock_and_put_state_no_creds():
    """
    Tests that an exception is raised if the user is not logged in
    """

    # create a Representation object
    test_repr = Representation()

    # create a mock Replication target object
    mock_repl_target = MagicMock(spec=DummyReplicationTarget)

    # patch the get_creds function to return None
    with patch(
        "fractal.cli.controllers.auth.AuthenticatedController.get_creds"
    ) as mock_get_creds:
        mock_get_creds.return_value = None

        # call the function to raise an exception
        with pytest.raises(Exception) as e:
            await _lock_and_put_state(
                test_repr, "test_room_id", mock_repl_target, "test_state_type", {}
            )

    # verify that the exception raised matches what was expected
    assert str(e.value) == "No creds found not locking and putting state"


async def test_signals_lock_and_put_state_with_creds(logged_in_db_auth_controller, test_room_id):
    """
    Tests that put_state is called when the user is logged in and had valid creds.
    """

    # verify that get_creds returns valid creds
    assert AuthenticatedController.get_creds() is not None

    # create a Representation object
    test_repr = Representation()

    # create a mock Replication target object
    mock_repl_target = MagicMock(spec=DummyReplicationTarget)

    # mock the put_state function
    test_repr.put_state = AsyncMock()

    # create parameter variables
    test_dict = {"test": "dict"}
    test_type = "test_state_type"

    # call the function
    await _lock_and_put_state(test_repr, test_room_id, mock_repl_target, test_type, test_dict)

    # verify that put state was called with the parameters we created locally
    test_repr.put_state.assert_called_with(test_room_id, mock_repl_target, test_type, test_dict)


async def test_signals_lock_and_put_state_lock_error(logged_in_db_auth_controller, test_room_id):
    """
    Tests that an exception is raised if there is a lock error
    """

    # verify that get_creds returns valid creds
    assert AuthenticatedController.get_creds() is not None

    # create a Representation object
    test_repr = Representation()

    # create a mock Replication target object
    mock_repl_target = MagicMock(spec=DummyReplicationTarget)

    # mock the put_state function
    test_repr.put_state = AsyncMock()

    # create parameter variables
    test_dict = {"test": "dict"}
    test_type = "test_state_type"

    # patch the lock function to raise an error
    with patch(f"{FILE_PATH}.MatrixLock.lock", side_effect=LockAcquireError("test message")):
        # call the function to raise an error
        with pytest.raises(LockAcquireError) as e:
            await _lock_and_put_state(
                test_repr, test_room_id, mock_repl_target, test_type, test_dict
            )

    # verify that the error message matches what is expected
    assert str(e.value) == "test message"


def test_signals_update_target_state_no_update_incorrect_model_type():
    """
    Tests that the function returns if the model type is not a MatrixReplicationTarget
    """

    # create an instance of a class that is not a MatrixReplicationTarget
    not_db_or_repl_target_instance = NotDatabaseOrReplTarget()

    # patch the logger
    with patch(f"{FILE_PATH}.logger") as mock_logger:
        # call the function passing the non-MatrixReplicationTarget object
        update_target_state(
            not_db_or_repl_target_instance,  # type: ignore
            not_db_or_repl_target_instance,  # type: ignore
            created=False,
            raw=False,
        )

    # verify that the logger is never called
    mock_logger.info.assert_not_called()


def test_signals_update_target_state_no_update_created_or_raw():
    """
    Tests that the function returns if raw or created are passed as True
    """

    # create a mock matrix replication target
    instance = MagicMock(spec=MatrixReplicationTarget)

    # patch the logger
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

    # verify that the logger is never called
    mock_logger.info.assert_not_called()


def test_signals_update_target_state_no_update_not_primary():
    """
    Tests that the function returns of the primary attribute of the instance is False
    and the instance is a MatrixReplicationTarget
    """

    # create a mock MatrixReplicationTarget object
    instance = MagicMock(spec=MatrixReplicationTarget)

    # set primary to false
    instance.primary = False

    # mock the get function
    instance.metadata.get = MagicMock()

    # patch the logger
    with patch(f"{FILE_PATH}.logger") as mock_logger:
        # call the function
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
    """
    Tests that the function returns if the primary target doesnt exist or is not a
    MatrixReplicationTarget instance
    """

    # create a mock database and mock the primary_target function
    instance = MagicMock(spec=Database)
    instance.primary_target = MagicMock()

    # create a target that is not a MatrixReplicationTarget object
    target = MagicMock(spec=NotDatabaseOrReplTarget)
    target.metadata = MagicMock()
    target.metadata.get = MagicMock()

    # set primary_target to return the non-MatrixReplicationTarget object
    instance.primary_target.return_value = target

    # patch the logger
    with patch(f"{FILE_PATH}.logger") as mock_logger:
        # function should return due to it not being the correct model type
        update_target_state(
            instance,
            instance,
            created=False,
            raw=False,
        )

        # set primary_target to return None
        instance.primary_target.return_value = None

        # function should return due to primary_target returning None
        update_target_state(
            instance,
            instance,
            created=False,
            raw=False,
        )

    # verify that the logger.warning function was called twice
    mock_logger.warning.call_count = 2

    # verify that the room_id was never fetched using get
    target.metadata.get.assert_not_called()


def test_signals_update_target_state_no_update_no_room_id():
    """
    Tests that the target state is not updated if there is no room id
    """

    # create a mock replication target and set primary to True
    instance = MagicMock(spec=MatrixReplicationTarget)
    instance.primary = True
    instance.metadata = MagicMock()

    # set the get function to return None
    instance.metadata.get = MagicMock(return_value=None)

    # patch the logger
    with patch(f"{FILE_PATH}.logger") as mock_logger:
        update_target_state(
            instance,
            instance,
            created=False,
            raw=False,
        )

    # verify that get was called
    instance.metadata.get.assert_called_once()

    # verify that logger.warning was called
    mock_logger.warning.assert_called_once()


def test_signals_update_target_state_target_update():
    """
    Test the case of a successful target update
    """

    # create a mock replication target
    instance = MagicMock(spec=MatrixReplicationTarget)
    instance.primary = True

    # mock the to_fixture function
    instance.to_fixture = MagicMock()
    instance.to_fixture.return_value = {}

    # mock the get_representation_module function
    instance.get_representation_module = MagicMock()
    instance.get_representation_module.return_value = "test_return_value"

    # mock the metadata
    instance.metadata = MagicMock()
    instance.metadata.get = MagicMock(return_value="test_room_id")

    # create a mock representation object
    mock_repr_instance = MagicMock(spec=Representation)

    # set the expected type
    expected_type = "f.database.target"

    # patch the logger
    with patch(f"{FILE_PATH}.logger") as mock_logger:
        # patch the _get_repr_instance function
        with patch(
            "fractal_database.models.RepresentationLog._get_repr_instance",
            new=MagicMock(return_value=mock_repr_instance),
        ):
            # patch lock_and_put_state
            with patch(f"{FILE_PATH}._lock_and_put_state") as mock_lock_and_put_state:
                update_target_state(
                    instance,
                    instance,
                    created=False,
                    raw=False,
                )

    # verify that lock and put state was called with the expected arguments
    mock_lock_and_put_state.assert_called_with(
        mock_repr_instance, "test_room_id", instance, expected_type, {"fixture": {}}
    )


def test_signals_update_target_state_db_update():
    """
    Tests the case of a successful database update
    """

    # create a mock database object
    instance = MagicMock(spec=Database)

    # create a mock replication target object
    primary_target = MagicMock(spec=MatrixReplicationTarget)

    # set the datatabase's primary_target function to return the mock replication target object
    instance.primary_target = MagicMock(return_value=primary_target)

    # mock the to_fixture function
    instance.to_fixture = MagicMock()
    instance.to_fixture.return_value = {}

    # mock the get_representation_module function
    primary_target.get_representation_module = MagicMock()
    primary_target.get_representation_module.return_value = "test_return_value"

    # mock the target's metadata
    primary_target.metadata = MagicMock()
    primary_target.metadata.get = MagicMock(return_value="test_room_id")

    # create a mock Representation object
    mock_repr_instance = MagicMock(spec=Representation)

    # set the expected type
    expected_type = "f.database"

    # patch the _get_repr_instance function
    with patch(
        "fractal_database.models.RepresentationLog._get_repr_instance",
        new=MagicMock(return_value=mock_repr_instance),
    ):
        # patch the _lock_and_put_state function
        with patch(f"{FILE_PATH}._lock_and_put_state") as mock_lock_and_put_state:
            update_target_state(
                instance,
                instance,
                created=False,
                raw=False,
            )

    # verify that lock and put state was called with the expected arguments
    mock_lock_and_put_state.assert_called_with(
        mock_repr_instance, "test_room_id", primary_target, expected_type, {"fixture": {}}
    )


def test_signals_zip_django_app_successful_zip():
    """
    Tests the case of a successful directory zip
    """

    # create an app directory and open a python file in it
    app1 = "app1"
    test_dir = FRACTAL_EXPORT_DIR
    os.makedirs(f"{test_dir}/{app1}", exist_ok=True)
    os.makedirs(f"{test_dir}/extracted", exist_ok=True)
    with open(f"{test_dir}/{app1}/xyz.py", "w"):
        pass

    # create AppConfig config object
    mock_app_config = MagicMock(spec=AppConfig)

    # set the path of the app config object
    mock_app_config.path = f"{test_dir}/{app1}"
    mock_app_config.name = "test_name"

    # zip the app config's file path, which is app1
    zip_django_app(mock_app_config)

    # verify that a zip file was created
    assert os.path.exists(f"{test_dir}/{mock_app_config.name}.tar.gz")

    # extract the contents of the zip file
    with tarfile.open(f"{test_dir}/{mock_app_config.name}.tar.gz", "r:gz") as tar:
        result = tar.extractall(f"{test_dir}/extracted")

    # store the file names in a list
    all_files = []
    for root, dirs, files in os.walk(f"{test_dir}/extracted"):
        all_files.extend(files)

    # verify that a pyproject.toml file and the python script is in the tarball
    assert "pyproject.toml" in all_files
    assert "xyz.py" in all_files


def test_signals_zip_django_app_empty_app_dir():
    """
    Tests the case where the target directory to be zipped is empty
    """

    # create an app directory and set the AppConfig file path
    app1 = "app1"
    test_dir = FRACTAL_EXPORT_DIR
    os.makedirs(f"{test_dir}/{app1}", exist_ok=True)
    os.makedirs(f"{test_dir}/extracted", exist_ok=True)
    mock_app_config = MagicMock(spec=AppConfig)
    mock_app_config.path = f"{test_dir}/{app1}"
    mock_app_config.name = "test_name"

    # verify that there is not a pyproject.toml in the app folder
    assert not os.path.exists(f"{mock_app_config.path}/pyproject.toml")

    # patch the tarfile add function
    with patch(f"{FILE_PATH}.tarfile.TarFile.add") as mock_tar_add:
        zip_django_app(mock_app_config)

    # verify that the add function was not called
    mock_tar_add.assert_not_called()

    # verify that the tarball was created
    assert os.path.exists(f"{test_dir}/{mock_app_config.name}.tar.gz")

    # extract the contents of the tarball
    with tarfile.open(f"{test_dir}/{mock_app_config.name}.tar.gz", "r:gz") as tar:
        result = tar.extractall(f"{test_dir}/extracted")

    # store the file names in a list
    all_files = []
    for root, dirs, files in os.walk(f"{test_dir}/extracted"):
        all_files.extend(files)

    # verify that a pyproject.toml was created and that it is the only file in the tarball
    assert os.path.exists(f"{test_dir}/extracted/pyproject.toml")
    assert len(files) == 1


def test_signals_zip_django_app_existing_pyproject():
    """
    Tests the case where there is already an existing pyproject in the app directory
    """

    # create an app directory
    app1 = "app1"
    test_dir = FRACTAL_EXPORT_DIR
    os.makedirs(f"{test_dir}/{app1}", exist_ok=True)
    os.makedirs(f"{test_dir}/extracted", exist_ok=True)

    # create a pyproject.toml and a python file in the app directory
    with open(f"{test_dir}/{app1}/pyproject.toml", "w"):
        pass
    with open(f"{test_dir}/{app1}/xyz.py", "w"):
        pass

    # create an AppConfig object and set the path to the app directory
    mock_app_config = MagicMock(spec=AppConfig)
    mock_app_config.path = f"{test_dir}/{app1}"
    mock_app_config.name = "test_name"

    # patch the init_poetry_project function
    with patch(f"{FILE_PATH}.init_poetry_project") as mock_init_poetry_project:
        zip_django_app(mock_app_config)

    # verify that the tarball was created
    assert os.path.exists(f"{test_dir}/{mock_app_config.name}.tar.gz")

    # extract the contents of the tarball
    with tarfile.open(f"{test_dir}/{mock_app_config.name}.tar.gz", "r:gz") as tar:
        result = tar.extractall(f"{test_dir}/extracted")

    # store the file names in a list
    all_files = []
    for root, dirs, files in os.walk(f"{test_dir}/extracted"):
        all_files.extend(files)

    # verify that the poetry project function was never called
    mock_init_poetry_project.assert_not_called()

    # verify the pyproject.toml and python script are in the list
    assert "pyproject.toml" in all_files
    assert "xyz.py" in all_files


async def test_signals_upload_app_wrong_file_type():
    """
    Tests that the function returns if the incorrect file type is passed
    """

    # create a mock replication target
    mock_primary_target = MagicMock(spec=MatrixReplicationTarget)
    mock_primary_target.aget_creds = AsyncMock()

    # create an incorrect file type string
    wrong_file_type = "test.txt"
    room_id = "test_room_id"

    # create a mock representation objectg
    mock_repr_instance = MagicMock(spec=Representation)

    # call the function passing the incorrect file type
    await _upload_app(
        room_id=room_id,
        app=wrong_file_type,
        repr_instance=mock_repr_instance,
        primary_target=mock_primary_target,
    )

    # verify that the function returns before aget_creds is called
    mock_primary_target.aget_creds.assert_not_called()


async def test_signals_upload_app_functional_test(test_database):
    """
    Tests that _lock_and_put_state is called if the correct file type is given and
    there no errors elsewhere in the function
    """

    # get the database's primary target
    primary_target = await sync_to_async(test_database.primary_target)()
    room_id = primary_target.metadata["room_id"]

    # get a valid file string
    file = "test.tar.gz"

    # create a mock representation object
    mock_repr = MagicMock(spec=Representation)

    # set an expected return
    upload_return = secrets.token_hex(8)

    # patch the upload file function of the FractalAsyncClient class
    with patch("fractal.matrix.FractalAsyncClient.upload_file") as mock_upload_file:
        # patch _lock_and_put_state
        with patch(f"{FILE_PATH}._lock_and_put_state") as mock_lock_and_put:
            mock_upload_file.return_value = upload_return
            await _upload_app(room_id, file, mock_repr, primary_target)

    # verify that upload_file was called
    mock_upload_file.assert_called_once()

    # verify that _lock_and_put_state arguments
    mock_lock_and_put.assert_called_once_with(
        mock_repr,  # type:ignore
        room_id,
        primary_target,
        f"f.database.app.test",
        {"mxc": upload_return},
    )


def test_signals_upload_exported_apps_filenotfound():
    """
    Tests that the function returns if a FileNotFoundError is caught
    """

    # patch current_db
    with patch('fractal_database.models.Database.current_db') as mock_current_db:
        # set os.listdir to raise an Error
        with patch(f"{FILE_PATH}.os.listdir", side_effect=FileNotFoundError()) as mock_listdir:
            upload_exported_apps()

    # verify that current_db was never called, meaning the functioned returned due to a
            # FileNotFoundError
    mock_current_db.assert_not_called()


def test_signals_upload_exported_apps_db_doesnotexist():
    """
    Tests that the function returns if there is no database
    """

    with pytest.raises(Database.DoesNotExist):
        database = Database.current_db()

    # patch the os library
    with patch(f"{FILE_PATH}.os") as mock_os:
        # set os.listdir to return True
        with patch('fractal_database.models.Database.primary_target') as mock_primary_target:
            mock_os.listdir = MagicMock(return_value=True)
            upload_exported_apps()

    # verify that primary_target was not called, meaning the function returned
            # while trying to fetch the current database
    mock_primary_target.assert_not_called()


def test_signals_upload_exported_apps_no_primary_target(test_database):
    """
    Tests that the function returns if the primary target doesn't exist
    """

    # patch os
    with patch(f"{FILE_PATH}.os") as mock_os:
        mock_os.listdir = MagicMock(return_value=True)
        # patch primary_target to return None
        with patch("fractal_database.models.Database.primary_target") as mock_primary_target:
            mock_primary_target.return_value = None
            with patch(f"{FILE_PATH}.isinstance") as mock_isinstance:
                upload_exported_apps()

    # verify that isinstance is never called, meaning the function returned when attempting
            # to fetch the primary target
    mock_isinstance.assert_not_called()


def test_signals_upload_exported_apps_primary_target_wrong_type(test_database):
    """
    Tests that the function returns when the primary type is not a MatrixReplicationTarget
    """

    # patch os
    with patch(f"{FILE_PATH}.os") as mock_os:
        mock_os.listdir = MagicMock(return_value=True)
        # patch primary_target to return a non-MatrixReplicationTarget object
        with patch("fractal_database.models.Database.primary_target") as mock_primary_target:
            
            # make a mock object that is not a MatrixReplicationTarget
            mock_wrong_type = MagicMock(spec=NotDatabaseOrReplTarget)
            mock_wrong_type.get_representation_module = MagicMock()
            mock_primary_target.return_value = mock_wrong_type
            assert mock_primary_target.return_value
            upload_exported_apps()

    # verify that the mock object's get_representation_module function was not called
    mock_wrong_type.get_representation_module.assert_not_called()


def test_signals_upload_exported_apps_no_tar_gz(test_database, test_device):
    """
    Tests that _upload_app is not called if the file type doesn't end with ".tar.gz"
    """

    # create app directories
    app1 = "app1"
    app2 = "app2"
    app3 = "app3"
    os.mkdir(FRACTAL_EXPORT_DIR)
    os.mkdir(f"{FRACTAL_EXPORT_DIR}/{app1}")
    os.mkdir(f"{FRACTAL_EXPORT_DIR}/{app2}")
    os.mkdir(f"{FRACTAL_EXPORT_DIR}/{app3}")

    # patch async_to_sync, which is used to call _upload_app
    with patch(f"{FILE_PATH}.async_to_sync") as mock_sync:
        upload_exported_apps()

    # verify that async_to_sync is never called
    mock_sync.assert_not_called()


def test_signals_upload_exported_apps_tar_gz(test_database, test_device):
    """
    Tests that _upload_app is called when the apps end with ".tar.gz"
    """

    # create app tarballs
    app1 = "app1.tar.gz"
    app2 = "app2.tar.gz"
    app3 = "app3.tar.gz"

    # create an export directory
    os.mkdir(FRACTAL_EXPORT_DIR)

    # create the app files
    with open(f"{FRACTAL_EXPORT_DIR}/{app1}", "w") as f:
        pass
    with open(f"{FRACTAL_EXPORT_DIR}/{app2}", "w") as f:
        pass
    with open(f"{FRACTAL_EXPORT_DIR}/{app3}", "w") as f:
        pass

    # patch the _upload_app function
    with patch(f"{FILE_PATH}._upload_app") as mock_upload:
        upload_exported_apps()

    # verify that _upload_app was called 3 times
    assert mock_upload.call_count == 3
