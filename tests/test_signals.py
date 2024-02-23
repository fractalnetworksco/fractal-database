import os
from django.db import transaction
import socket
import random
import secrets
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.conf import settings
from fractal.cli.controllers.auth import AuthenticatedController
from fractal_database.models import (  # MatrixCredentials,
    Database,
    Device,
    DummyReplicationTarget,
)
from fractal_database.signals import (
    _accept_invite,
    clear_deferred_replications,
    commit,
    create_database_and_matrix_replication_target,
    defer_replication,
    enter_signal_handler,
    increment_version,
    object_post_save,
    register_device_account,
    schedule_replication_on_m2m_change,
)
from fractal_database_matrix.models import MatrixReplicationTarget

pytestmark = pytest.mark.django_db(transaction=True)

FILE_PATH = "fractal_database.signals"


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

    TODO: combine exit and enter signal handler
    """

    nest_count = random.randint(1, 100)

    with patch(f"{FILE_PATH}._thread_locals", new=MagicMock()) as mock_thread:
        mock_thread.signal_nesting_count = nest_count
        enter_signal_handler()

    assert mock_thread.signal_nesting_count == nest_count + 1


def test_signals_commit_replication_error():
    """ """

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
    assert call_args["target"] == Database.current_db().primary_target()
    assert call_args["device"] == mock_device


# @pytest.mark.skip(reason="not properly getting the data from the db in the test for verification")
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
            with patch(f"{FILE_PATH}.exit_signal_handler") as mock_exit:
                result = object_post_save(
                    sender=second_test_device,
                    instance=test_device,
                    created=False,
                    raw=False,
                )

    assert result is None
    mock_exit.assert_called_once()
    mock_logger.info.assert_called_with(f"Back inside post_save for instance: {test_device}")


def test_signals_object_post_save_not_in_nested_signal_handler(test_device, second_test_device):
    """ """
    test_device.schedule_replication = MagicMock()

    with patch(f"{FILE_PATH}.logger") as mock_logger:
        with patch(f"{FILE_PATH}.in_nested_signal_handler", return_value=False):
            with patch(f"{FILE_PATH}.exit_signal_handler") as mock_exit:
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


async def test_signals_schedule_replication_on_m2m_change_invalid_action(
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


async def test_signals_schedule_replication_on_m2m_change_empty_pk_set(
    test_device, second_test_device
):
    """
    #? pass pk as empty list
    """

    sender = test_device
    instance = second_test_device

    sender.save = MagicMock()
    sender.schedule_replication = MagicMock()

    with patch(f"{FILE_PATH}.print") as mock_print:
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


async def test_signals_schedule_replication_on_m2m_change_true_reverse(
    test_device, second_test_device
):
    """
    #? set reverse to True
    """

    sender = test_device
    instance = second_test_device

    sender.save = MagicMock()
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

    sender.save.assert_not_called()
    sender.schedule_replication.assert_called_once_with(created=False)
    instance.schedule_replication.assert_called_once_with(created=False)


async def test_signals_schedule_replication_on_m2m_change_false_reverse(
    test_device, second_test_device
):
    """
    #? set reverse to false
    """

    sender = test_device
    instance = second_test_device

    instance.save = MagicMock()
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

    instance.save.assert_called_once()
    instance.schedule_replication.assert_not_called()
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
    """
    """

    # import pdb; pdb.set_trace()
    creds = AuthenticatedController.get_creds()

    db_project_name = os.path.basename(settings.BASE_DIR)
    from fractal_database.signals import get_deferred_replications
    print('here=========', get_deferred_replications())

    # if there are creds, os.environ will not be used
    create_database_and_matrix_replication_target()

    d = Database.objects.get(name=db_project_name)

    target = d.primary_target()

    assert isinstance(target, MatrixReplicationTarget)

    assert target.metadata["room_id"]

    device = d.devices.get()

    assert socket.gethostname().lower() in device.name


@pytest.mark.skip(reason="not testing this correctly")
async def test_signals_accept_invite_successful_join(test_matrix_creds):
    """ """

    room_id = test_matrix_creds.id
    # _accept_invite(test_matrix_creds, )
