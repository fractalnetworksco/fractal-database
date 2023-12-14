import functools
import logging
import os
import sys
from typing import Any, Callable

import django
from django.conf import settings
from fractal.cli import FRACTAL_DATA_DIR

logger = logging.getLogger(__name__)


def use_django(func: Callable[..., Any]):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        args = [self] + list(args)
        sys.path.append(os.path.join(FRACTAL_DATA_DIR, "rootdb"))
        os.environ["DJANGO_SETTINGS_MODULE"] = "rootdb.settings"
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
