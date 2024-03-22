import asyncio
import logging
import subprocess
import sys
from io import StringIO
from typing import TYPE_CHECKING

from django.core.management import call_command
from django.core.management.commands.loaddata import Command as loaddata_command
from django.db import DEFAULT_DB_ALIAS
from fractal_database_matrix.broker import broker

if TYPE_CHECKING:
    from fractal_database.models import AppInstanceConfig

logger = logging.getLogger(__name__)


def load_data_from_dicts(fixture: str) -> None:
    """
    Load data into Django models from a Django fixture string.

    Args:
    - fixture (str): A Django fixture encoded as a string.
    - project_dir (str): The path to the project directory.
    """
    from django.conf import settings

    logger.warning(f"Loading {fixture} into local database")

    # project_dir = settings.BASE_DIR
    # cmd = [sys.executable, f"{project_dir}/manage.py", "loaddata", "--format=json", "-"]
    # proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    # fixture_bytes = fixture.encode("utf-8")

    # stdout, stderr = proc.communicate(input=fixture_bytes)

    # if proc.returncode != 0:
    #     raise Exception(f"ERROR {proc.returncode}: Failed to load data: {stdout}")

    # logger.info(stdout.decode("utf-8"))

    # load the fixture using loaddata
    # NOTE: monkey patching this loaddata command instance to hand it the fixture file
    # in memory. This is a workaround for the fact that call_command() doesn't
    # support passing in a file-like object. This is necessary for using loaddata in tests
    fixture_file = StringIO(fixture)
    loaddata = loaddata_command()
    loaddata.compression_formats["stdin"] = (lambda *args: fixture_file, None)  # type: ignore
    try:
        loaddata.handle(
            "-",
            format="json",
            ignore=False,
            database=DEFAULT_DB_ALIAS,
            exclude=[],
            app_label=None,
            verbosity=1,
        )
    except Exception as e:
        raise Exception(f"ERROR: Failed to load data: {e}")

    # call_command("loaddata", "--format=json", "-", fixture_file)

    return None


@broker.task(queue="replication")
async def replicate_fixture(fixture: str) -> None:
    """
    Replicates a given fixture into the local database.

    Args:
    - fixture (str): A Django fixture encoded as a string.
    - project_dir (str): The path to the project directory.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, load_data_from_dicts, fixture)


async def launch_app(app_config: "AppInstanceConfig", *args, **kwargs) -> None:
    """ """
    print(f"Launching app {app_config.app.name} with config {app_config}")
