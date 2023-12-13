import functools
import os
import sys
from typing import Any, Callable

import django
from fractal.cli import FRACTAL_DATA_DIR


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
