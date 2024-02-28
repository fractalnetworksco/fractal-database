from builtins import NotImplementedError
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fractal_database import representations
from fractal_database.models import RepresentationLog
from fractal_database.representations import Representation, get_nested_attr


@pytest.mark.skip("test is not being detected in dict")
async def test_get_nested_attr_test_period_split():
    sample_object = {"test": {"nested": "value"}, "testing": "two"}
    sample_attr_path = "test.nested"

    result = representations.get_nested_attr(obj=sample_object, attr_path=sample_attr_path)


@pytest.mark.skip("test is not being detected in dict")
async def test_get_nested_attr_path_no_period():
    sample_object = {"test": {"nested": "value"}, "testing": "two"}
    sample_attr_path = "test"
    result = representations.get_nested_attr(obj=sample_object, attr_path=sample_attr_path)


async def test_create_representation_logs_returns_correct_result():
    mock_instance = MagicMock()
    mock_target = MagicMock()
    mock_representation_log = MagicMock()

    mock_create_method = MagicMock(return_value=mock_representation_log)
    RepresentationLog.objects.create = mock_create_method

    result = Representation.create_representation_logs(mock_instance, mock_target)
    mock_create_method.assert_called_once_with(
        instance=mock_instance,
        method=Representation.representation_module,
        target=mock_target,
        metadata=mock_instance.repr_metadata_props(),
    )
    assert result == [mock_representation_log]


@pytest.mark.skip(
    "Mock is wrong? Not getting into put_state function. Something weird with Representation class?"
)
async def test_put_state_notimplementederror():
    mock = Representation()
    mock.put_state = AsyncMock()
    with pytest.raises(NotImplementedError) as e:
        await mock.put_state()
