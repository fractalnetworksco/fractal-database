import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fractal_database.replication import tasks


def test_load_data_from_dicts_correct_return():
    sample_fixture_json = "json_fixture"
    with patch("fractal_database.replication.tasks.subprocess.Popen") as mock_popen:
        mock_popen.return_value.communicate.return_value = (b"", b"")
        mock_popen.return_value.returncode = 0
        return_value = tasks.load_data_from_dicts(fixture=sample_fixture_json)
    assert return_value is None


def test_load_data_from_dicts_raise_exception():
    sample_fixture_json = "This fixture will fail"
    mock_popen = MagicMock()
    mock_popen.communicate.return_value = ("", "Failed to load data")
    mock_popen.returncode = 1
    tasks.subprocess.Popen = MagicMock(return_value=mock_popen)
    with pytest.raises(Exception) as e:
        tasks.load_data_from_dicts(fixture=sample_fixture_json)
    assert "Failed to load data" in str(e.value)


@pytest.mark.asyncio
async def test_replicate_fixture():
    sample_fixture_json = "json_fixture"
    mock_load_data_from_dicts = AsyncMock()
    with patch(
        "fractal_database.replication.tasks.load_data_from_dicts", mock_load_data_from_dicts
    ):
        await tasks.replicate_fixture(fixture=sample_fixture_json)
        mock_load_data_from_dicts.assert_called_once_with(sample_fixture_json)
