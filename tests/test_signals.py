import random
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fractal_database.models import Device, DummyReplicationTarget
from fractal_database.signals import (
    clear_deferred_replications,
    commit,
    defer_replication,
    enter_signal_handler,
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


# @pytest.mark.skip(reason="attribute error")
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


# @pytest.mark.skip(reason="same attribute error as above")
def test_signals_commit_no_error():
    """ """

    repl_target = DummyReplicationTarget()
    repl_target.name = "test_name"

    with patch(f"{FILE_PATH}.logger", new=MagicMock()) as mock_logger:
        with patch(f"{FILE_PATH}.clear_deferred_replications", new=MagicMock()) as mock_clear:
            commit(repl_target)

    mock_clear.assert_called_with(repl_target.name)
    mock_logger.error.assert_not_called()


@pytest.mark.django_db()
def test_signals_register_device_account_not_created_or_raw(test_device):
    """ """
    print("name===========", test_device.name)
