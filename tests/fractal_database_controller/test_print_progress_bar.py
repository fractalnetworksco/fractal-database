import pytest
from datetime import timedelta
from fractal_database.controllers.fractal_database_controller import FractalDatabaseController, TransferMonitor
from unittest.mock import MagicMock

@pytest.mark.skip(reason='not sure how to test this')
def test_print_progress_bar_no_monitor():
    """
    """

    db_controller = FractalDatabaseController()
    mock_monitor = MagicMock(spec=TransferMonitor)
    # mock_monitor.remaining_time = None
    # mock_monitor.average_speed = 0

    time = timedelta(seconds=5)
    mock_monitor.average_speed = 10
    mock_monitor.remaining_time = time

    db_controller.print_progress_bar(
        iteration=5,
        total=10,
        monitor=mock_monitor
    )

