import os

import appdirs

HOMESERVER_CLIENT_NAME = os.environ.get("HOMESERVER_CLIENT_NAME", "matrix")
HOMESERVER_URL = os.environ.get("HOMESERVER_URL", "http://localhost:8008")
HOMESERVER_DEVICE_GROUP = os.environ.get("HOMESERVER_DEVICE_GROUP", "My Devices")
HOMESERVER_DATABASE_PATH = os.environ.get(
    "HOMESERVER_DATABASE_PATH", f"{appdirs.user_data_dir('homeserver')}/cache"
)
PYTHON_BIN = os.environ.get("PYTHON_BIN", "python")
