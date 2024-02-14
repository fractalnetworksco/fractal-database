"""
This script is intended to be ran by the test container's entrypoint.

Ensures that the provided test user exists and creates a room for testing.
On Success, writes necessary environment variables to .env.testing.
"""

import asyncio
import os
from sys import exit

import docker
from aiofiles import open
from docker.models.containers import Container
from nio import LoginError, RoomCreateError
from fractal.cli.controllers.auth import AuthController
from asgiref.sync import sync_to_async
from fractal.matrix.async_client import FractalAsyncClient

ENV = os.environ.get("ENV", "dev")
TEST_CONFIG_DIR = os.environ.get("TEST_CONFIG_DIR", ".")
TEST_ENV_FILE = os.environ.get("TEST_ENV_FILE", f"{TEST_CONFIG_DIR}/fractal_database.{ENV}.env")
TEST_HOMESERVER_URL = os.environ.get("TEST_HOMESERVER_URL", "http://localhost:8008")
TEST_USER_USERNAME = os.environ.get("TEST_USER_USERNAME", "admin")
TEST_USER_PASSWORD = os.environ.get("TEST_USER_PASSWORD", "admin")
PYTHON_BIN = os.environ.get("PYTHON_BIN", "venv/bin/python")
SYNAPSE_DOCKER_LABEL = os.environ.get("SYNAPSE_DOCKER_LABEL", "org.homeserver=true")


async def main():
    try:
        # get homeserver container
        docker_client = docker.from_env()
        synapse_container = docker_client.containers.list(
            filters={"label": SYNAPSE_DOCKER_LABEL}
        )[0]
        # asserting here so that the Container type hint works : )
        assert isinstance(synapse_container, Container)
    except Exception:
        print("No homeserver container found")
        print("Launch synapse container in /synapse")
        exit(1)

    # create admin user on synapse if it doesn't exist
    result = synapse_container.exec_run(
        f"register_new_matrix_user -c /data/homeserver.yaml -a -u {TEST_USER_USERNAME} -p {TEST_USER_PASSWORD} http://localhost:8008"
    )

    if "User ID already taken" not in result.output.decode("utf-8") and result.exit_code != 0:
        print(result.output.decode("utf-8"))
        exit(1)

    # login
    matrix_client = FractalAsyncClient(
        TEST_HOMESERVER_URL, access_token="", user=TEST_USER_USERNAME
    )

    print(f"Logging in to homeserver: {TEST_HOMESERVER_URL} as {TEST_USER_USERNAME}")
    login_res = await matrix_client.login(TEST_USER_PASSWORD)
    if isinstance(login_res, LoginError):
        print(f"Error logging in: {login_res.message}")
        exit(1)

    # disable rate limiting for the created test user
    print(f"Disabling rate limiting for user: {matrix_client.user_id}")
    await matrix_client.disable_ratelimiting(matrix_client.user_id)

    # This always creates a new room. This is okay since we want a fresh start
    print("Creating room")
    room_create_res = await matrix_client.room_create(name="Test Room")
    if isinstance(room_create_res, RoomCreateError):
        print(f"Error creating room: {room_create_res.message}")
        exit(1)

    # write environment file
    async with open(TEST_ENV_FILE, "w") as f:
        await f.write(
            f'export HS_USER_ID="{matrix_client.user_id}"\nexport MATRIX_ROOM_ID="{room_create_res.room_id}"\nexport MATRIX_ACCESS_TOKEN="{matrix_client.access_token}"\nexport MATRIX_HOMESERVER_URL="{TEST_HOMESERVER_URL}"\nexport PYTHON_BIN="{PYTHON_BIN}"\nexport HS_OWNER_ID="{matrix_client.user_id}"\nexport HS_DEVICE_ID="{matrix_client.user_id}"\n'
        )

    await matrix_client.close()

    print("Successfully prepared")



    auth_controller = AuthController()

    await sync_to_async(auth_controller.login)(
        matrix_id=matrix_client.user_id,
        homeserver_url=TEST_HOMESERVER_URL,
        access_token=matrix_client.access_token
    )

if __name__ == "__main__":
    asyncio.run(main())
