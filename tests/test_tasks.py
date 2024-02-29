from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fractal_database.replication import tasks


@pytest.mark.skip("Just started working on")
async def test_load_data_from_dicts_return_none():
    with patch("subprocess.Popen") as mock_Popen:
        mock_Popen


def test_load_data_from_dicts_raise_exception():
    sample_fixture_json = "This fixture will fail"
    with pytest.raises(Exception) as e:
        tasks.load_data_from_dicts(fixture=sample_fixture_json)
    assert f"ERROR 1: Failed to load data: None" in str(e.value)
