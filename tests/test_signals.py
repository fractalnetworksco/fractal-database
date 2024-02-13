import random
from unittest.mock import AsyncMock, MagicMock, patch

from fractal_database.models import ReplicationTarget
from fractal_database.signals import (
    clear_deferred_replications,
    commit,
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


def test_signals_commit_replication_error():
    """ """

    mock_target = MagicMock(spec=ReplicationTarget)
    mock_target.replicate = AsyncMock()

    mock_target.replicate.side_effect = Exception()

    with patch(f"{FILE_PATH}.logger", new=MagicMock()) as mock_logger:
        commit(mock_target)

        #! failing in the finally block, thread local has no attr named deferred replications
