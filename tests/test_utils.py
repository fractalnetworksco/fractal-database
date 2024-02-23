import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fractal_database.utils import get_project_name, use_django

FILE_PATH = "fractal_database.utils"


def test_utils_use_django_no_project_name():
    """ """

    @use_django
    async def test_use_django():
        """ """
        print("using django")


def test_utils_get_project_name_attribute_error():
    """ """

    with patch(f"{FILE_PATH}.settings", side_effect=AttributeError) as mock_settings:
        with patch(f"{FILE_PATH}.logger") as mock_logger:
            delattr(mock_settings, "PROJECT_NAME")
            proj = get_project_name()

    mock_logger.warning.assert_called_with(
        "settings.PROJECT_NAME is not set. Defaulting to settings.BASE_DIR"
    )


def test_utils_get_project_name_no_error():
    """ """

    expected_name = secrets.token_hex(8)
    with patch(f"{FILE_PATH}.settings") as mock_settings:
        mock_settings.PROJECT_NAME = expected_name
        with patch(f"{FILE_PATH}.logger") as mock_logger:
            proj = get_project_name()
    
    assert proj == expected_name
    mock_logger.assert_not_called()
