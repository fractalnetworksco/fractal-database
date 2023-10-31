import asyncio
import os
from typing import Any, Dict, Tuple

import aiofiles
import appdirs
import yaml
from aiofiles.os import makedirs

data_dir = appdirs.user_data_dir("homeserver")


async def write_user_data(data: dict, filename: str) -> None:
    """
    Write data to yaml file <filename> in user's appdir (ie ~/.local/share/homeserver)
    """
    await makedirs(data_dir, exist_ok=True)

    try:
        data = yaml.dump(data)
    except yaml.YAMLError as error:
        raise error

    user_data = os.path.join(data_dir, filename)
    async with aiofiles.open(user_data, "w") as file:
        await file.write(data)


async def read_user_data(filename: str) -> Tuple[Dict[str, Any], str]:
    """
    Reads data from <filename> in user's appdir (ie ~/.local/share/homeserver)

    TODO: Support multiple file types. Right now this only supports yaml files.

    Returns:
        (user_data, data_file_path): Data in file (as dict), path to file (str).
    """
    data_file_path = os.path.join(data_dir, filename)

    try:
        async with aiofiles.open(data_file_path, "r") as file:
            user_data = await file.read()
    except FileNotFoundError as error:
        raise error

    try:
        user_data = yaml.safe_load(user_data)
    except yaml.YAMLError as error:
        raise error

    return user_data, data_file_path


def run_in_async(func, *args, **kwargs) -> Any:
    """
    Runs an async function in an asyncio event loop.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(func, *args, **kwargs)
