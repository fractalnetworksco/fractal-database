from builtins import NotImplementedError
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fractal_database import representations
from fractal_database.models import RepresentationLog
from fractal_database.representations import Representation, get_nested_attr


# Sample class used for get_nested_attr testing, as it expects an object
class SampleObject:
    def __init__(self, **kwargs):
        # Iterates over each key:value pair
        for key, value in kwargs.items():
            setattr(self, key, value)


# Don't need to test attribute path with no period because recursively calls nested attribute which goes into else statement
async def test_get_nested_attr_test_period_split():
    sample_object = SampleObject(test=SampleObject(nested="value"), testing="two")
    sample_attr_path = "test.nested"

    result = representations.get_nested_attr(obj=sample_object, attr_path=sample_attr_path)

    assert result == "value"


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


async def test_put_state_notimplementederror_correct():
    representation_instance = Representation()
    args = ()
    kwargs = {}
    with pytest.raises(NotImplementedError) as e:
        await representation_instance.put_state(*args, **kwargs)
    assert "" in str(e.value)
