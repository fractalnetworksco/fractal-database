import asyncio
import json
import os
import subprocess
import sys
from typing import Any, Dict, List

from django.conf import settings
from fractal import FractalAsyncClient
from fractal_database_matrix.broker import broker


def load_data_from_dicts(data_list: List[Dict[str, Any]]) -> None:
    """
    Load data into Django models from a list of dictionaries. Dictionaries
    should be in the fixture format

    Args:
    - data_list (list[dict]): List of dictionaries representing model instances
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "homeserver.app.settings")
    project_dir = settings.BASE_DIR
    # project_root_path = os.path.dirname(project_dir)
    cmd = [sys.executable, f"{project_dir}/manage.py", "loaddata", "--format=json", "-"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    objects = json.dumps(data_list).encode("utf-8")
    stdout, stderr = proc.communicate(input=objects)

    if proc.returncode != 0:
        raise Exception(f"ERROR: {proc.returncode} Failed to load data: {stderr}")
    else:
        print(stdout.decode("utf-8"))

    return None


@broker.task(queue="replication")
async def replicate_fixture(event: str, room_id: str, event_type: str):
    print(f"Replicating {event} to room {room_id} with event type {event_type}")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, load_data_from_dicts, json.loads(event))
