import asyncio
import logging
import subprocess
import sys
from typing import TYPE_CHECKING

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

    logger.debug(f"Loading {fixture} into local database")

    project_dir = settings.BASE_DIR
    cmd = [sys.executable, f"{project_dir}/manage.py", "loaddata", "--format=json", "-"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    fixture_bytes = fixture.encode("utf-8")

    stdout, stderr = proc.communicate(input=fixture_bytes)

    if proc.returncode != 0:
        raise Exception(f"ERROR {proc.returncode}: Failed to load data: {stderr}")

    logger.info(stdout.decode("utf-8"))

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
