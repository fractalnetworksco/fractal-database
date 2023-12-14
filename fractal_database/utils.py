import functools
import logging
import os
import sys
from typing import Any, Callable

import django
from django.conf import settings
from fractal.cli import FRACTAL_DATA_DIR
from fractal.cli.utils import read_user_data

logger = logging.getLogger(__name__)


def use_django(func: Callable[..., Any]):
    """
    Decorator for CLI commands that use Django. This decorator ensures that the
    correct Django settings are loaded and that the correct project is loaded
    into the sys.path.

    This decorator should be used for any CLI command that uses Django.

    NOTE: If you have multiple projects, you must specify the project name as an
    environment variable FRACTAL_PROJECT_NAME.
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        args = [self] + list(args)
        projects, _ = read_user_data("projects.yaml")
        if len(projects) > 1:
            project_name = os.environ.get("FRACTAL_PROJECT_NAME")
            if not project_name:
                raise Exception(
                    "Multiple projects found. Please specify a FRACTAL_PROJECT_NAME as an environment variable"
                )
        else:
            project_name = list(projects.keys())[0]
        sys.path.append(os.path.join(FRACTAL_DATA_DIR, project_name))
        os.environ["DJANGO_SETTINGS_MODULE"] = f"{project_name}.settings"
        django.setup()
        res = func(*args, **kwargs)
        return res

    return wrapper


def get_project_name():
    try:
        project_name = settings.PROJECT_NAME
    except AttributeError:
        logger.warning("settings.PROJECT_NAME is not set. Defaulting to settings.BASE_DIR")
        project_name = os.path.basename(settings.BASE_DIR)
    return project_name
