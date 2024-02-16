import random
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fractal_database.models import Device, DummyReplicationTarget
from fractal_database.signals import (
    clear_deferred_replications,
    commit,
    defer_replication,
    enter_signal_handler,
    register_device_account,
)

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


@pytest.mark.django_db()
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


@pytest.mark.django_db()
def test_signals_register_device_account_test(
    test_device, second_test_device, test_homeserver_url, test_user_access_token
):
    """ """

    test_matrix_id = "@admin:localhost"

    with patch(f"{FILE_PATH}.AuthenticatedController") as mock_auth_controller:
        with patch(f"{FILE_PATH}.FractalAsyncClient") as mock_client:
            mock_client.
            mock_auth_controller.get_creds = MagicMock()
            mock_auth_controller.get_creds.return_value = [test_user_access_token, test_homeserver_url, test_matrix_id]
            register_device_account(
                sender=test_device, instance=second_test_device, created=False, raw=False
            )
