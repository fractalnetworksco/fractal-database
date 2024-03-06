import secrets
from unittest.mock import patch
from fractal_database.utils import get_project_name

FILE_PATH = "fractal_database.utils"

def test_get_project_attribute_error():
    """ 
    Tests that an exception is raised if there is no project name set
    """

    # patch the settings in the utils file
    with patch(f"{FILE_PATH}.settings", side_effect=AttributeError) as mock_settings:
        # patch the logger
        with patch(f"{FILE_PATH}.logger") as mock_logger:
            # delete the project name attribute of the settings object
            delattr(mock_settings, "PROJECT_NAME")

            # call get_project_name
            proj = get_project_name()

    # verify that logger.warning was called
    mock_logger.warning.assert_called_with(
        "settings.PROJECT_NAME is not set. Defaulting to settings.BASE_DIR"
    )


def test_get_project_no_error():
    """ 
    Tests the case where there is no error fetching the project name
    """

    # generate a random name
    expected_name = secrets.token_hex(8)

    # mock the settings object in the utils file
    with patch(f"{FILE_PATH}.settings") as mock_settings:
        # set the generated name as the proejct name in the settings object
        mock_settings.PROJECT_NAME = expected_name
        
        # patch the logger
        with patch(f"{FILE_PATH}.logger") as mock_logger:
            proj = get_project_name()

    
    # verify that the project name that is returned matches the expected name
    assert proj == expected_name

    # verify that logger.warning was not called
    mock_logger.warning.assert_not_called()