import os
import pytest
from typing import Optional, Tuple
from fractal_database.utils import use_django
from fractal_database.models import Database
from fractal.cli.utils import data_dir, write_user_data, read_user_data
from fractal.cli import FRACTAL_DATA_DIR
from unittest.mock import patch, MagicMock

FILE_PATH = "fractal_database.utils"

@pytest.mark.skip(reason='not a test function, only used for the wrapper')
@use_django
async def test_django_decorator(self, project_name: str):
    """
    """
    d = Database.objects.aget()

    return d is not None

async def test_use_django_filenotfound(test_database):
    """
    """

    assert not os.path.exists(os.path.join(data_dir, 'projects.yaml'))

    with pytest.raises(FileNotFoundError):
        result = await test_django_decorator(test_database)


async def test_use_django_more_than_one_project_no_project_name(test_database, test_yaml_dict):
    """

    """
    write_user_data(test_yaml_dict, "projects.yaml")
    assert os.path.exists(os.path.join(data_dir, 'projects.yaml'))

    with patch(f"{FILE_PATH}.os.environ.get", return_value=None) as mock_os_get:
        with pytest.raises(Exception) as e:
            result = await test_django_decorator(test_database)




async def test_use_django_setup_error(test_database, test_yaml_dict):
    """
    """

    write_user_data(test_yaml_dict, "projects.yaml")
    assert os.path.exists(os.path.join(data_dir, 'projects.yaml'))

    with patch.dict(os.environ, {"FRACTAL_PROJECT_NAME": test_yaml_dict['FRACTAL_PROJECT_NAME']}, clear=True): 
        with patch(f"{FILE_PATH}.django.setup") as mock_setup:
            mock_setup.side_effect = Exception()
            with pytest.raises(Exception):
                result = await test_django_decorator(test_database)


async def test_use_django_wrapper_returned(test_database, test_yaml_dict):
    """
    """

    write_user_data(test_yaml_dict, "projects.yaml")
    assert os.path.exists(os.path.join(data_dir, 'projects.yaml'))

    with patch.dict(os.environ, {"FRACTAL_PROJECT_NAME": test_yaml_dict['FRACTAL_PROJECT_NAME']}, clear=True): 
        result = await test_django_decorator(test_database)

    # function is returned, meaning the wrapper worked correctly and was returned
    assert result


async def test_use_django_exactly_one_project(test_database):
    """
    """

    test_yaml_dict = {"FRACTAL_PROJECT_NAME": "test_project_name"}

    write_user_data(test_yaml_dict, "projects.yaml")

    assert os.path.exists(os.path.join(data_dir, 'projects.yaml'))

    projects, _ = read_user_data("projects.yaml")
    assert len(projects) == 1

    await test_django_decorator(test_database)