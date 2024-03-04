import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fractal_database.replication import tasks


def test_load_data_from_dicts_correct_return():
    sample_fixture_json = "json_fixture"
    mock_popen = MagicMock(spec=subprocess.Popen)
    # Communicate returns a tuple of bytes which is why we use b""
    mock_popen.communicate.return_value = (b"", b"")
    # 0 = success|1 = failure
    mock_popen.returncode = 0
    tasks.subprocess.Popen = MagicMock(return_value=mock_popen)
    with patch("fractal_database.replication.tasks.logger", new=MagicMock()) as mock_logger:
        return_value = tasks.load_data_from_dicts(fixture=sample_fixture_json)
    assert return_value == None


def test_load_data_from_dicts_raise_exception():
    sample_fixture_json = "This fixture will fail"
    mock_popen = MagicMock(spec=subprocess.Popen)
    mock_popen.communicate.return_value = ("", "Failed to load data")
    mock_popen.returncode = 1
    tasks.subprocess.Popen = MagicMock(return_value=mock_popen)
    with pytest.raises(Exception) as e:
        tasks.load_data_from_dicts(fixture=sample_fixture_json)
    assert "Failed to load data" in str(e.value)


@pytest.mark.asyncio
async def test_replicate_fixture():
    # Sample fixture JSON
    sample_fixture_json = "json_fixture"

    # Mocking load_data_from_dicts function
    mock_load_data_from_dicts = AsyncMock()

    # Patching tasks.load_data_from_dicts with the mock
    with patch(
        "fractal_database.replication.tasks.load_data_from_dicts", mock_load_data_from_dicts
    ):
        # Call the replicate_fixture function
        await tasks.replicate_fixture(fixture=sample_fixture_json)

        # Assert that load_data_from_dicts was called with the sample fixture JSON
        mock_load_data_from_dicts.assert_called_once_with(sample_fixture_json)
