from fractal_database.signals import enter_signal_handler
from unittest.mock import patch, MagicMock, AsyncMock
import random

FILE_PATH = "fractal_database.signals"

def test_signals_enter_signal_handler_no_nesting_count():
    """
    Tests that if the _thread_locals object does not have a signal_nesting_count attribute,
    one is created for it an incremented to 1.
    """

    with patch(f'{FILE_PATH}._thread_locals', new=MagicMock()) as mock_thread:
        delattr(mock_thread, "signal_nesting_count")

        assert not hasattr(mock_thread, 'signal_nesting_count')
        enter_signal_handler()
        assert hasattr(mock_thread, 'signal_nesting_count')
        assert mock_thread.signal_nesting_count == 1

def test_signals_enter_signal_handler_existing_nesting_count():
    """
    """

    nest_count = random.randint(0, 100)

    with patch(f'{FILE_PATH}._thread_locals', new=MagicMock()) as mock_thread:
        mock_thread.signal_nesting_count = nest_count
        enter_signal_handler()
        assert mock_thread.signal_nesting_count == nest_count + 1


