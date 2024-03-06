import os
import pytest
from fractal_database.utils import use_django
from fractal_database.models import Database
from fractal.cli.utils import data_dir, write_user_data, read_user_data

FILE_PATH = "fractal_database.utils"

async def test_use_django_filenotfound(test_database):
    """
    """

    assert not os.path.exists(os.path.join(data_dir, 'projects.yaml'))

    with pytest.raises(FileNotFoundError):
        @use_django
        async def test_django_decorator():
            """
            """
            d = Database.objects.get()

        await test_django_decorator(test_database)

async def test_use_django_more_than_one_project(test_database, test_yaml_dict):
    """
    """
    #! gotta delete this file after every use, its passing when it shouldnt be
    # write_user_data(test_yaml_dict, "projects.yaml")
    assert os.path.exists(os.path.join(data_dir, 'projects.yaml'))