import functools
import io
import logging
import os
import sys
from typing import Any, Callable, Optional

import django
import toml
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
        try:
            django.setup()
        except Exception as e:
            logger.error(f"Error setting up Django: {e}")

        kwargs["project_name"] = project_name
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


def init_poetry_project(project_name: str, in_memory: bool = False) -> Optional[io.BytesIO]:
    """
    Initialize a new poetry project in the current directory.

    Args:
        project_name (str): The name of the project
        in_memory (bool): If True, the project will be created in memory and returned as a BytesIO object.
    """
    pyproject_toml = f"""\
[build-system]
requires = [ "poetry-core",]
build-backend = "poetry.core.masonry.api"

[tool.poetry]
name = "{project_name}"
version = "0.1.0"
authors = ["FIX ME <email@email.com>"]
description = "Generated by Fractal Networks"

[tool.fractal]

[tool.poetry.dependencies]
python = "^3.11"
django = ">=4.0.0"
fractal-database = ">=0.0.1"
"""
    # return the rendered toml in memory if in_memory is True
    if in_memory:
        return io.BytesIO(pyproject_toml.encode("utf-8"))

    with open("pyproject.toml", "w") as f:
        f.write(pyproject_toml)
