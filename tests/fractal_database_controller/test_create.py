from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import os
from uuid import uuid4

import pytest
from fractal_database.controllers.fractal_database_controller import (
    FractalDatabaseController,
    FRACTAL_DATA_DIR,
)

FILE_PATH = "fractal_database.controllers.fractal_database_controller"
FRACTAL_PATH = "fractal.matrix.FractalAsyncClient"

#! ==================================
#? NOT DONE
#! ==================================

def test_create_FileFoundError(_use_django):
    """
    """

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    with patch(f"{FILE_PATH}.os.mkdir", side_effect=FileExistsError) as mock_mkdir:
        with patch(f"{FILE_PATH}.os.getcwd") as mock_getcwd:
            with pytest.raises(SystemExit):
                controller.create('test_database')

    mock_getcwd.assert_called_once()

@pytest.mark.django_db(transaction=True)
def test_create_db_created(_use_django, temp_directory):
    """
    """

    project = 'mytestapp'
    
    os.chdir(temp_directory)
    path = os.path.join(f"{os.getcwd()}/{project}")

    # create a FractalDatabaseController object
    controller = FractalDatabaseController()

    try:
        controller.create(project)
    except:
        raise
