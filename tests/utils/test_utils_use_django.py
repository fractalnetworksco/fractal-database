import os
from typing import Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest
from fractal.cli import FRACTAL_DATA_DIR
from fractal.cli.utils import data_dir, read_user_data, write_user_data
from fractal_database.models import Database
from fractal_database.utils import use_django

FILE_PATH = "fractal_database.utils"

pytestmark = pytest.mark.django_db(transaction=True)


@use_django
async def django_decorator(self, project_name: str):
    """
    Makes use of the @use_django decorator
    """

    d = await Database.objects.aget()

    return d is not None


async def test_use_django_filenotfound(test_database):
    """
    Tests that the function raises an exception if there is no projects.yaml file
    """

    # verify that there is no projects.yaml file in the data directory
    assert not os.path.exists(os.path.join(data_dir, "projects.yaml"))

    # call the function to raise an exception
    with pytest.raises(FileNotFoundError):
        result = await django_decorator(test_database)


async def test_use_django_more_than_one_project_no_project_name(test_database, test_yaml_dict):
    """
    Tests the case where there is more than 1 project in the projects.yaml file, causing
    the function to fetch the project name from the environment variable but is unable to
    access it in the dictionary.
    """

    # create a projects.yaml file
    write_user_data(test_yaml_dict, "projects.yaml")

    # verify that the file exists in the data directory
    assert os.path.exists(os.path.join(data_dir, "projects.yaml"))

    # patch the os.environ.get function to return None
    with patch(f"{FILE_PATH}.os.environ.get", return_value=None) as mock_os_get:
        # call the function to raise an exception
        with pytest.raises(Exception) as e:
            result = await django_decorator(test_database)


async def test_use_django_setup_error(test_database, test_yaml_dict):
    """
    Tests that an exception is raised if there is an error during django setup
    """

    # create the projects.yaml file
    write_user_data(test_yaml_dict, "projects.yaml")

    # verify that the file exists in the data directory
    assert os.path.exists(os.path.join(data_dir, "projects.yaml"))

    # patch the os.environ dictionary to include a fractal project
    with patch.dict(
        os.environ, {"FRACTAL_PROJECT_NAME": test_yaml_dict["test_project"]}, clear=True
    ):
        # patch django.setup to raise an exception
        with patch(f"{FILE_PATH}.django.setup") as mock_setup:
            mock_setup.side_effect = Exception()

            # call the function to raise an exception
            with pytest.raises(Exception):
                result = await django_decorator(test_database)


async def test_use_django_wrapper_returned(test_database, test_yaml_dict):
    """
    Tests that the function returns the wrapper if there are no errors
    """

    # create the projects.yaml file
    write_user_data(test_yaml_dict, "projects.yaml")

    # verify that the file exists in the data directory
    assert os.path.exists(os.path.join(data_dir, "projects.yaml"))

    # patch the os.environ dictionary to include a fractal project
    with patch.dict(
        os.environ, {"FRACTAL_PROJECT_NAME": test_yaml_dict["test_project"]}, clear=True
    ):
        result = await django_decorator(test_database)

    # the wrapper is returned by use_django, meaning that the django_decorator function runs as well
    assert result


async def test_use_django_exactly_one_project(test_database):
    """
    Tests the case where there is exactly 1 project in the yaml file
    """

    # create a dictionary for a yaml file
    test_yaml_dict = {"FRACTAL_PROJECT_NAME": "test_project_name"}

    # create the projects.yaml file
    write_user_data(test_yaml_dict, "projects.yaml")

    # verify the file exists on the data directory
    assert os.path.exists(os.path.join(data_dir, "projects.yaml"))

    # read in the yaml file
    projects, _ = read_user_data("projects.yaml")

    # verify that there is only one project present in the file
    assert len(projects) == 1

    # call the function and assert it returns True
    assert await django_decorator(test_database)
