import os
import random
import secrets
from django.conf import settings
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fractal_database.models import Device, DummyReplicationTarget, Database
from fractal_database.signals import (
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
    """

    nest_count = random.randint(1, 100)

    with patch(f"{FILE_PATH}._thread_locals", new=MagicMock()) as mock_thread:
        mock_thread.signal_nesting_count = nest_count
        enter_signal_handler()

    assert mock_thread.signal_nesting_count == nest_count + 1
    assert mock_thread.signal_nesting_count is not 1


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

        # only raw is False
        register_device_account(
            sender=test_device, instance=second_test_device, created=True, raw=False
        )

        # only created is False
        register_device_account(
            sender=test_device, instance=second_test_device, created=False, raw=True
        )

    mock_logger.info.assert_not_called()


@pytest.mark.skip(reason="not entering the nested function at all")
def test_signals_register_device_account_with_creds(
    test_device, second_test_device, test_homeserver_url, test_user_access_token
):
    """
    FIXME: figure out how to mock the classes imported within the function
    """

    test_matrix_id = "@admin:localhost"
    test_registration_token = "test_registration_token"

    with patch("fractal.cli.controllers.auth.AuthenticatedController") as mock_auth_controller:
        # with patch('fractal.matrix.MatrixClient') as mock_client:

        # mock_client.generate_registration_token = AsyncMock()
        # mock_client.generate_registration_token.return_value = test_registration_token

        # mock_client.whoami = AsyncMock()
        # mock_client.user_id = test_matrix_id

        # mock_client.register_with_token = AsyncMock()

        mock_auth_controller.get_creds = MagicMock()
        mock_auth_controller.get_creds.return_value = [
            test_user_access_token,
            test_homeserver_url,
            test_matrix_id,
        ]

        print("calling***************")
        register_device_account(
            sender=test_device, instance=second_test_device, created=False, raw=False
        )

    # mock_client.whoami.assert_not_called()


@pytest.mark.skip(reason="not properly getting the data from the db in the test for verification")
def test_signals_increment_version(test_device, second_test_device):
    """ """

    original_version = test_device.object_version

    increment_version(sender=second_test_device, instance=test_device)

    updated_device = test_device.objects.get(pk=test_device.pk)

    assert updated_device.object_version == original_version + 1


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


def test_signals_object_post_save_verify_recursive_call(test_device, second_test_device):
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

    not_comparison_touple = (f"Back inside post_save for instance: {test_device}",)
    comparison_touple = (f"Outermost post save instance: {test_device}",)
    assert not_comparison_touple not in args
    assert comparison_touple in args
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
    Device.objects.get = MagicMock(return_value=sender)

    result = schedule_replication_on_m2m_change(
        sender=sender,
        instance=instance,
        action="post_add",
        reverse=True,
        model=Device,  # type: ignore
        pk_set=ids,
    )

    sender.save.assert_not_called()
    sender.schedule_replication.assert_called_once()
    instance.schedule_replication.assert_called_once()


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
    Device.objects.get = MagicMock(return_value=sender)

    result = schedule_replication_on_m2m_change(
        sender=sender,
        instance=instance,
        action="post_add",
        reverse=False,
        model=Device,  # type: ignore
        pk_set=ids,
    )

    instance.save.assert_called_once()
    instance.schedule_replication.assert_not_called()
    sender.schedule_replication.assert_not_called()


def test_signals_create_database_and_matrix_replication_target_verify_recursive_call():
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

    create_database_and_matrix_replication_target()


def test_signals_create_database_and_matrix_replication_target_no_creds_no_os_environ():
    """ """

    with patch(
        f"fractal.cli.controllers.auth.AuthenticatedController.get_creds", return_value=None
    ):
        with patch.dict(os.environ, {}, clear=True):
            with patch(f"{FILE_PATH}.logger") as mock_logger:
                create_database_and_matrix_replication_target()

    mock_logger.info.assert_called_with(
        "MATRIX_HOMESERVER_URL and/or MATRIX_ACCESS_TOKEN not set, skipping MatrixReplicationTarget creation"
    )


def test_signals_create_database_and_matrix_replication_target_no_creds_verify_os_environ():
    """ """

    db_project_name = os.path.basename(settings.BASE_DIR)
    with pytest.raises(Database.DoesNotExist):
        Database.objects.get(name=db_project_name)

    create_database_and_matrix_replication_target()

    d = Database.objects.get(name=db_project_name)

    assert d.name == db_project_name
    target = d.primary_target()

    assert isinstance(target, MatrixReplicationTarget)

    assert target.metadata['room_id']


def test_signals_create_database_and_matrix_replication_target_with_creds():
    """ """

    with patch(
        "fractal.cli.controllers.auth.AuthenticatedController.get_creds",
        return_value=("test_access_token", "test_homeserver", "test_owner_id"),
    ):
        with patch(
            "fractal_database_matrix.models.MatrixReplicationTarget.objects.get_or_create"
        ) as mock_get_or_create:
            create_database_and_matrix_replication_target()
