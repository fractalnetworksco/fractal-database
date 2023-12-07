import asyncio
import importlib
import os
import subprocess
from sys import exit
from typing import Any, Dict, Optional

import docker
import docker.api.build
import toml
from django.core.management import call_command
from django.core.management.base import CommandError
from fractal.cli import cli_method
from fractal.cli.controllers.authenticated import AuthenticatedController, auth_required
from fractal.cli.utils import data_dir
from fractal.matrix import MatrixClient, parse_matrix_id

GIT_ORG_PATH = "https://github.com/fractalnetworksco"
DEFAULT_FRACTAL_SRC_DIR = os.path.join(data_dir, "src")
FRACTAL_BASE_IMAGE = "fractalnetworksco/base:base"


class FractalDatabaseController(AuthenticatedController):
    """
    FIXME: AuthenticatedController REQUIRES that user is logged in to
    use ANY of the subcommands. This is not ideal for an offline-first app.
    Probably should use an @authenticated decorator instead.

    Controller that runs when no subcommands are passed.

    Responsible for launching the Homeserver agent's sync loop.
    """

    PLUGIN_NAME = "db"

    async def _invite_user(self, user_id: str, room_id: str) -> None:
        async with MatrixClient(homeserver_url=self.homeserver_url, access_token=self.access_token) as client:  # type: ignore
            await client.invite(user_id, room_id)

    async def _join_room(self, room_id: str) -> None:
        async with MatrixClient(homeserver_url=self.homeserver_url, access_token=self.access_token) as client:  # type: ignore
            await client.join_room(room_id)

    @auth_required
    @cli_method
    def invite(self, user_id: str, room_id: str, admin: bool = False):
        """
        Invite a Matrix user to a database.
        ---
        Args:
            user_id: The user ID to invite to the room.
            room_id: The room ID to invite the user to.
            admin: Whether or not the user should be made an admin of the room. (FIXME)

        """
        if not admin:
            # FIXME
            raise Exception("FIXME! Fractal Database requires that all users must be admin")

        # verify that provided user_id is a valid matrix id
        parse_matrix_id(user_id)[0]
        asyncio.run(self._invite_user(user_id, room_id))

        print(f"Successfully invited {user_id} to {room_id}")

    @auth_required
    @cli_method
    def join(self, room_id: str):
        """
        Accept an invitation to a database or knock if not invited yet.
        ---
        Args:
            room_id: The room ID to join.

        """
        # TODO: When joining fails and the reason is that the user isn't invited,
        # handle knocking on the room
        asyncio.run(self._join_room(room_id))
        print(f"Successfully joined {room_id}")

    @cli_method
    def init(self, app: Optional[str] = None):
        """
        Starts a new Fractal Database project for this machine.
        Located in ~/.local/share/fractal/rootdb
        ---
        Args:
            app: The name of the database to start. If not provided, a root database is started.

        """
        if app:
            try:
                importlib.import_module(app)
            except ModuleNotFoundError:
                print(f"Failed to find app {app}. Is it installed?")
                exit(1)

        os.makedirs(data_dir, exist_ok=True)
        os.chdir(data_dir)
        try:
            if app:
                call_command("startproject", "appdb")
            else:
                call_command("startproject", "rootdb")
        except CommandError:
            print("You have already initialized Fractal Database on your machine.")
            exit(1)

        # add fractal_database to INSTALLED_APPS
        if app:
            to_write = (
                f"INSTALLED_APPS += ['{app}', 'fractal_database_matrix', 'fractal_database']\n"
            )
        else:
            to_write = "INSTALLED_APPS += ['fractal_database_matrix', 'fractal_database']\n"

        file_path = "appdb/appdb/settings.py" if app else "rootdb/rootdb/settings.py"
        with open(file_path, "a") as f:
            f.write(to_write)

        print(f"Successfully initialized Fractal Database project {data_dir}/{app or 'rootdb'}")

    @cli_method
    def startapp(self, db_name: str):
        """
        Create a database Python module (Django app). Equivalent to `django-admin startapp`.
        ---
        Args:
            db_name: The name of the database to start.

        """
        print(f"Creating Fractal Database Django app for {db_name}...")
        try:
            os.mkdir(db_name)
        except FileExistsError:
            # get full path to db_name
            full_path = os.path.join(os.getcwd(), db_name)
            print(f"Failed to start app: Directory {full_path} already exists.")
            exit(1)

        os.chdir(db_name)
        call_command("startapp", db_name)
        subprocess.run(["poetry", "init", "-n", f"--name={db_name}"])

        pyproject = toml.loads(open("pyproject.toml").read())

        # have to add dependencies without using poetry
        pyproject["tool"]["poetry"]["dependencies"][
            "django"
        ] = ">=4.0.0"  # FIXME: Hardcoded version
        pyproject["tool"]["poetry"]["dependencies"][
            "fractal-database"
        ] = ">=0.0.1"  # FIXME: Hardcoded version
        pyproject["tool"]["fractal"] = {}
        with open("pyproject.toml", "w") as f:
            f.write(toml.dumps(pyproject))

        # poetry init puts a readme key in the toml, so
        # create a readme so that the app is installable
        with open(f"README.md", "w") as f:
            f.write(f"# Django App Generated By Fractal Database\n")

        print("Done.")

    def _verify_repos_cloned(self, source_dir: str = DEFAULT_FRACTAL_SRC_DIR):
        """
        Verifies that all Fractal Database projects are cloned into the user data directory.
        """
        projects = [
            "fractal-database-matrix",
            "fractal-database",
            "taskiq-matrix",
            "fractal-matrix-client",
        ]
        for project in projects:
            if not os.path.exists(os.path.join(source_dir, project)):
                print(f"Failed to find {project} in {source_dir}.")
                print("Run `fractal db clone` to clone all Fractal Database projects.")
                return False
        return True

    @cli_method
    def clone(self):
        """
        Clones all Fractal Database projects into the user data directory.

        ---
        Args:

        """
        source_dir = os.environ.get("FRACTAL_SOURCE_DIR", str(DEFAULT_FRACTAL_SRC_DIR))

        if source_dir == DEFAULT_FRACTAL_SRC_DIR:
            os.mkdir(DEFAULT_FRACTAL_SRC_DIR)
            source_dir = DEFAULT_FRACTAL_SRC_DIR

        try:
            subprocess.run(["git", "clone", f"{GIT_ORG_PATH}/fractal-cli.git"], cwd=source_dir)
            subprocess.run(
                ["git", "clone", f"{GIT_ORG_PATH}/fractal-database-matrix.git"], cwd=source_dir
            )
            subprocess.run(
                ["git", "clone", f"{GIT_ORG_PATH}/fractal-database.git"], cwd=source_dir
            )
            subprocess.run(["git", "clone", f"{GIT_ORG_PATH}/taskiq-matrix.git"], cwd=source_dir)
            subprocess.run(
                ["git", "clone", f"{GIT_ORG_PATH}/fractal-matrix-client.git"], cwd=source_dir
            )
        except Exception as e:
            print(f"Failed to clone Fractal Database projects: {e}")
            return False

    @cli_method
    def build_base(self, verbose: bool = False):
        """
        Builds a base Docker image with all Fractal Database projects installed.
        Built image is tagged as fractalnetworksco/base:base

        ---
        Args:
            verbose: Whether or not to print verbose output.
        """
        original_dir = os.getcwd()
        if not self._verify_repos_cloned():
            self.clone()

        os.chdir(os.environ.get("FRACTAL_SOURCE_DIR", str(DEFAULT_FRACTAL_SRC_DIR)))

        dockerfile = """
FROM python:3.11.4
RUN mkdir /fractal
COPY . /fractal
RUN pip install /fractal/fractal-cli/
RUN pip install /fractal/fractal-matrix-client/
RUN pip install /fractal/taskiq-matrix/
RUN pip install /fractal/fractal-database-matrix/
RUN pip install /fractal/fractal-database/
"""
        client = docker.from_env()

        # FIXME: Have to monkey patch in order to build from in-memory Dockerfiles correctly
        docker.api.build.process_dockerfile = lambda dockerfile, path: ("Dockerfile", dockerfile)

        print(f"Building Docker image {FRACTAL_BASE_IMAGE}...")
        response = client.api.build(
            path=".",
            dockerfile=dockerfile,
            forcerm=True,
            tag=FRACTAL_BASE_IMAGE,
            quiet=False,
            decode=True,
            nocache=True,
        )
        for line in response:
            if "stream" in line:
                if verbose:
                    print(line["stream"], end="")

        os.chdir(original_dir)
        print(f"Successfully built Docker image {FRACTAL_BASE_IMAGE}.")

    def _get_fractal_app(self) -> Dict[str, Any]:
        # ensure current directory is a fractal app
        try:
            with open("pyproject.toml") as f:
                pyproject = toml.loads(f.read())
                pyproject["tool"]["fractal"]
        except FileNotFoundError:
            print("Failed to find pyproject.toml in current directory.")
            print("You must be in the directory where pyproject.toml is located.")
            raise Exception("Failed to find pyproject.toml in current directory.")
        except KeyError:
            print("Failed to find fractal key in pyproject.toml.")
            print("This project must be a Fractal Database app.")
            raise Exception("Failed to find fractal key in pyproject.toml.")
        return pyproject

    def _build(self, name: str, verbose: bool = False) -> str:
        """
        Builds a given database into a Docker container and exports it as a tarball.

        ---
        Args:
            image_tag: The Docker image tag to build.
            verbose: Whether or not to print verbose output.
        """
        try:
            self._get_fractal_app()
        except Exception:
            exit(1)

        client = docker.from_env()
        image_tag = f"{name}:fractal-database"

        # ensure base image is built
        if client.images.list(name=FRACTAL_BASE_IMAGE) == []:
            self.build_base(verbose=verbose)

        dockerfile = f"""
FROM {FRACTAL_BASE_IMAGE}
RUN mkdir /code
COPY . /code
RUN pip install /code

RUN fractal db init --app {name}
"""
        # FIXME: Have to monkey patch in order to build from in-memory Dockerfiles correctly
        docker.api.build.process_dockerfile = lambda dockerfile, path: ("Dockerfile", dockerfile)

        print(f"Building Docker image {image_tag}...")
        response = client.api.build(
            path=".",
            dockerfile=dockerfile,
            forcerm=True,
            tag=image_tag,
            quiet=False,
            decode=True,
            nocache=True,
        )
        for line in response:
            if "stream" in line:
                if verbose:
                    print(line["stream"], end="")
        return image_tag

    @auth_required
    @cli_method
    def deploy(self, verbose: bool = False):
        """
        Builds a given database into a Docker container and exports it as a tarball, and
        uploads it to the Fractal Matrix server.

        Must be in the directory where pyproject.toml is located.
        ---
        Args:
            verbose: Whether or not to print verbose output.

        """
        path = "."
        # load pyproject.toml to get project name
        try:
            pyproject = self._get_fractal_app()
        except Exception:
            exit(1)

        try:
            name = pyproject["tool"]["poetry"]["name"]
        except Exception as e:
            print(f"Failed to load pyproject.toml: {e}")
            exit(1)

        image_tag = self._build(name, verbose=verbose)

        path = os.getcwd()
        print(f"\nExtracting image as tarball in {path}")
        try:
            subprocess.run(["docker", "save", "-o", f"{name}.tar", image_tag])
        except Exception as e:
            print(f"Failed to extract image: {e}")
            exit(1)

        # TODO: Push to Matrix Room

        print("Done.")


Controller = FractalDatabaseController
