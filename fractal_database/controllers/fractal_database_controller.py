import asyncio
import importlib
import json
import os
import socket
import subprocess
import sys
from functools import partial
from sys import exit
from typing import Any, Dict, Optional

import django
import docker
import docker.api.build
import requests
import toml
from asgiref.sync import sync_to_async
from clicz import cli_method
from django.core.management import call_command
from django.db import transaction
from fractal.cli import FRACTAL_DATA_DIR
from fractal.cli.controllers.auth import AuthenticatedController, auth_required
from fractal.cli.utils import data_dir, read_user_data, write_user_data
from fractal.matrix import MatrixClient
from fractal.matrix.utils import parse_matrix_id
from fractal_database.utils import init_poetry_project, use_django
from nio import (
    InviteInfo,
    InviteMemberEvent,
    InviteNameEvent,
    RoomGetStateEventError,
    TransferMonitor,
)
from taskiq.receiver.receiver import Receiver
from taskiq.result_backends.dummy import DummyResultBackend
from taskiq_matrix.matrix_queue import Task

GIT_ORG_PATH = "https://github.com/fractalnetworksco"
DEFAULT_FRACTAL_SRC_DIR = os.path.join(data_dir, "src")
FRACTAL_BASE_IMAGE = "fractalnetworksco/base:base"


class FractalDatabaseController(AuthenticatedController):
    PLUGIN_NAME = "db"

    async def _invite_user(self, user_id: str, room_id: str, admin: bool) -> None:
        async with MatrixClient(homeserver_url=self.homeserver_url, access_token=self.access_token) as client:  # type: ignore
            await client.invite(user_id, room_id, admin=admin)

    async def _join_room(self, room_id: str) -> None:
        async with MatrixClient(homeserver_url=self.homeserver_url, access_token=self.access_token) as client:  # type: ignore
            await client.join_room(room_id)

    async def _upload_file(self, file: str, monitor: Optional[TransferMonitor] = None) -> str:
        async with MatrixClient(homeserver_url=self.homeserver_url, access_token=self.access_token) as client:  # type: ignore
            return await client.upload_file(file, monitor=monitor)

    async def _list_invites(self) -> Dict[str, InviteInfo]:
        async with MatrixClient(
            homeserver_url=self.homeserver_url, access_token=self.access_token
        ) as client:
            return await client.get_room_invites()

    async def _mxc_to_http(self, mxc_url: str) -> Optional[str]:
        async with MatrixClient(
            homeserver_url=self.homeserver_url, access_token=self.access_token
        ) as client:
            return await client.mxc_to_http(mxc_url)

    @use_django
    async def _sync_database_metadata(self, room_id: str, **kwargs) -> None:
        async with MatrixClient(homeserver_url=self.homeserver_url, access_token=self.access_token) as client:  # type: ignore
            fixture = []
            res = await client.room_get_state_event(room_id, "f.database")
            if isinstance(res, RoomGetStateEventError):
                raise Exception(res.message)
            try:
                database_fixture = json.loads(res.content["fixture"])[0]
                database_pk = database_fixture["pk"]
            except Exception as e:
                raise Exception(f"Failed to parse database fixture: {e}")
            fixture.append(database_fixture)

            res = await client.room_get_state_event(room_id, "f.database.target")
            if isinstance(res, RoomGetStateEventError):
                raise Exception(res.message)
            try:
                target_fixture = json.loads(res.content["fixture"])[0]
            except Exception as e:
                raise Exception(f"Failed to parse target fixture: {e}")

            added_target_pk = target_fixture["pk"]
            fixture.append(target_fixture)

        from fractal_database.replication.tasks import replicate_fixture

        try:
            await replicate_fixture(json.dumps(fixture))
        except Exception as e:
            raise Exception(f"Failed to load fixture: {e}")

        from fractal_database.models import Database, DatabaseConfig, Device
        from fractal_database_matrix.models import (
            MatrixCredentials,
            MatrixReplicationTarget,
        )
        from fractal_database_matrix.representations import MatrixExistingSubSpace

        try:
            # get the parent database
            database = await Database.acurrent_db()

            # if current database is the same as the one we are syncing, return
            # (dont want to create a representation for the same database)
            if database_pk == str(database.pk):
                return None

        except DatabaseConfig.DoesNotExist:
            # we are initializing an instance database
            def _init_instance_database():
                """
                Initialize an instance database
                """
                with transaction.atomic():
                    database = Database.objects.get(pk=database_pk)
                    DatabaseConfig.objects.create(current_db=database)
                    device = Device.objects.create(name=os.environ["FRACTAL_DEVICE_NAME"])
                    MatrixCredentials.objects.create(
                        access_token=os.environ["MATRIX_ACCESS_TOKEN"],
                        matrix_id=os.environ["MATRIX_USER_ID"],
                        target=database.primary_target(),
                        device=device,
                    )

            await sync_to_async(_init_instance_database)()
            return None

        target = await database.aprimary_target()
        target_to_add = await MatrixReplicationTarget.objects.select_related("database").aget(
            pk=added_target_pk
        )
        repr_log = await sync_to_async(MatrixExistingSubSpace.create_representation_logs)(
            target_to_add, target
        )

        await repr_log[0].apply()

        # TODO: Handle publishing a users homeserver as a target for the
        # synced in database

        return None

    async def _sync_data(self, room_id: str) -> None:
        from fractal_database_matrix.broker import broker

        # FIXME: create_filter should be moved onto the FractalAsyncClient
        from taskiq_matrix.filters import create_room_message_filter

        broker._init_queues()

        broker.replication_queue.checkpoint.since_token = None
        # dont need results for syncing tasks
        broker.result_backend = DummyResultBackend()  # type: ignore
        receiver = Receiver(broker=broker)

        while True:
            task_filter = create_room_message_filter(
                room_id, types=[broker.replication_queue.task_types.task]
            )
            tasks = await broker.replication_queue.get_tasks(timeout=0, task_filter=task_filter)
            print(f"Got tasks: {len(tasks)}")
            if not tasks:
                print("No more tasks")
                break

            # merge all replicated tasks into a single "merged" task
            # this prevents us from having to run each individual task
            merged_task: Optional[Task] = None
            fixture = []

            # FIXME: this assumes that all of the tasks received are the
            # same task. Should probably handle specifically the replicate_fixture
            # task.
            for task in tasks:
                if not merged_task:
                    merged_task = task

                data = json.loads(task.data["args"][0])
                for item in data:
                    fixture.append(item)

            merged_task.data["args"][0] = json.dumps(fixture)

            # keep syncing until we get no more tasks
            print(f"Got {len(tasks)} tasks")
            with open("tmp-fixture.json", "a") as f:
                f.write(json.dumps(fixture, indent=4))

            ackable_task = await broker.replication_queue.yield_task(
                merged_task, ignore_acks=True, lock=False
            )
            await receiver.callback(ackable_task)

    # async def _download_file(
    #     self, mxc_uri: str, save_path: os.PathLike, monitor: Optional[TransferMonitor] = None
    # ) -> None:
    #     async with MatrixClient(homeserver_url=self.homeserver_url, access_token=self.access_token) as client:  # type: ignore
    #         res = await client.download(mxc=mxc_uri, save_to=save_path, monitor=monitor)
    #         print(f"Got res: {res}")
    #         return None

    def print_progress_bar(
        self,
        iteration: int,
        total: int,
        prefix="Upload Progress: ",
        length=50,
        fill="█",
        monitor: Optional[TransferMonitor] = None,
    ):
        """
        Call this function to print the progress bar.

        :param iteration: current progress (e.g., bytes uploaded so far).
        :param total: total value to reach (e.g., total size of the file in bytes).
        :param prefix: prefix string.
        :param suffix: suffix string.
        :param length: character length of the bar.
        :param fill: bar fill character.
        """
        percent = ("{0:.1f}").format(100 * (iteration / float(total)))
        filled_length = int(length * iteration // total)
        bar = fill * filled_length + "-" * (length - filled_length)
        current_MB = iteration / (1024 * 1024)
        total_MB = total / (1024 * 1024)
        remaining_time = ""
        if monitor:
            remaining_time = monitor.remaining_time
        avg_speed = ""
        if monitor:
            avg_speed = f"{monitor.average_speed / (1024 * 1024):.2f}MB/s"

        if not remaining_time:
            estimated_time = "Calculating Remaining Time..."
        else:
            # pretty print time deltatime
            estimated_time = f"Estimated Time Remaining: {remaining_time.seconds // 60}m {remaining_time.seconds % 60}s"

        sys.stdout.write(
            f"\r{prefix} |{bar}| {percent}% ({current_MB:.2f}MB / {total_MB:.2f}MB @ {avg_speed}): {estimated_time}"
        )
        sys.stdout.flush()
        if iteration == total:
            print()

    def _print_file_progress(
        self, transferred: int, file_size: int, monitor: TransferMonitor
    ) -> None:
        self.print_progress_bar(transferred, file_size, monitor=monitor)

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
        asyncio.run(self._invite_user(user_id, room_id, admin))

        print(f"Successfully invited {user_id} to {room_id}")

    @auth_required
    @cli_method
    def list_invites(self):
        """
        List invites to rooms.
        TODO: Pretty print as a table
        ---

        """
        invites = asyncio.run(self._list_invites())
        for room_id, invite_info in invites.items():
            room_name = ""
            for event in invite_info.invite_state:
                # invite_state is a list of events. They usually come with 3 events:
                # 1. InviteNameEvent: this event will have the name of the room (m.room.name)
                # 2. InviteMemberEvent: this event is the membership event of the inviter. Not particularly useful
                #                       for us since the next event contains the actual invite membership for the invitee
                #                       as well as the user_id of the inviter.
                # 3. InviteMemberEvent: this event has the actual invite membership of the user (m.room.member). Contains
                #                       the user_id of the inviter.
                if isinstance(event, InviteNameEvent):
                    room_name = event.name
                elif isinstance(event, InviteMemberEvent) and event.membership == "invite":
                    print(f"{event.sender} invited you to {room_name} ({room_id})")
                    break

    @auth_required
    @cli_method
    def join(self, room_id: str, **kwargs):
        """
        Accept an invitation to a database or knock if not invited yet.
        ---
        Args:
            room_id: The room ID to join.

        """
        # TODO: When joining fails and the reason is that the user isn't invited,
        # handle knocking on the room
        asyncio.run(self._join_room(room_id))

        project_name = os.environ.get("FRACTAL_PROJECT_NAME", "fractaldb")

        # ensure project database exists and is migrated (FIXME: maybe not migrate... dunno)
        print(f"Verifying project database {project_name} is initialized...")
        self.init(project_name=project_name, exist_ok=True)

        # sync primary replication target from room state
        asyncio.run(self._sync_database_metadata(room_id))

        print(f"Successfully joined {room_id}")

    @cli_method
    def init(
        self,
        app: Optional[str] = None,
        project_name: Optional[str] = None,
        quiet: bool = False,
        no_migrate: bool = False,
        exist_ok: bool = False,
    ):
        """
        Starts a new Fractal Database project for this machine.
        Located in ~/.local/share/fractal/rootdb
        ---
        Args:
            app: The name of the database to start. If not provided, a root database is started.
            project_name: The name of the project to start. Defaults to app name if app is provided,
            quiet: Whether or not to print verbose output.
            no_migrate: Whether or not to skip initial migrations.
            exist_ok: Dont return error exit code if project already exists.
        """
        if not no_migrate and not self.access_token:
            # if applying migrations, then user must be logged in.
            # we dont want to get in a partially initialized state, then
            # fail due to user not being logged in when we
            # actually go to apply migrations later.
            print("You must be logged in to initialize a Fractal Database project.")
            exit(1)
        if app:
            try:
                importlib.import_module(app)
            except ModuleNotFoundError:
                print(f"Failed to find app {app}. Is it installed?")
                exit(1)

        os.makedirs(data_dir, exist_ok=True)

        os.chdir(data_dir)
        if not project_name:
            project_name = "appdb" if app else "fractaldb"

        if os.path.exists(f"{data_dir}/{project_name}"):
            if not exist_ok:
                print(
                    f'You have already initialized the Fractal Database project "{project_name}" on your machine.'
                )
                exit(1)
            return None

        try:
            import fractal_database

            # have to run in a subprocess instead of using call_command
            # due to the settings file being cached upon the first
            # invocation of call_command
            template_path = os.path.join(fractal_database.__path__[0], "templates", "project_template")  # type: ignore
            subprocess.run(["django-admin", "startproject", "--template", template_path, project_name], check=True)  # type: ignore
        except Exception as e:
            print(f'Error creating project "{project_name}" on your machine: {e}')
            exit(1)

        # generate and apply initial migrations
        if not no_migrate:
            self.migrate(project_name)
        try:
            projects, _ = read_user_data("projects.yaml")
        except FileNotFoundError:
            projects = {}

        projects[project_name] = {"name": project_name}
        write_user_data(projects, "projects.yaml")

        print(f"Successfully initialized Fractal Database project {data_dir}/{project_name}")

    @auth_required
    @cli_method
    def migrate(self, project_name: str):
        """
        Creates and applies database migrations for the given Fractal Database Django
        project

        ---
        Args:
            project_name: The name of the project to migrate.
        """
        sys.path.append(os.path.join(FRACTAL_DATA_DIR, project_name))
        os.environ["DJANGO_SETTINGS_MODULE"] = f"{project_name}.settings"
        django.setup()

        os.chdir(f"{FRACTAL_DATA_DIR}/{project_name}")

        call_command("makemigrations")
        call_command("migrate")

    @use_django
    @auth_required
    @cli_method
    def shell(self, **kwargs):
        """
        Exec into a Django loaded shell for the given Fractal Database Django project.

        ---
        Args:
            project_name: The name of the project to shell into.
        """
        # sys.path.append(os.path.join(FRACTAL_DATA_DIR, project_name))
        # os.environ["DJANGO_SETTINGS_MODULE"] = f"{project_name}.settings"
        # django.setup()

        # os.chdir(project_name)
        # TODO customize prompt based on current context
        # TODO autoload models
        init_shell = f"""import os
import IPython
from IPython.terminal.ipapp import load_default_config
import asyncio
import atexit
from IPython.terminal.prompts import Prompts, Token
from django.apps import apps
class ModelAccessor:
    def __init__(self):
        for app in apps.get_app_configs():
            for model in apps.get_models(app):
                setattr(self, model.__name__, model)
class CustomPrompt(Prompts):
    def in_prompt_tokens(self, cli=None):
        return [(Token.Prompt, '[{kwargs["project_name"]}]# ')]
    def out_prompt_tokens(self):
        return super().out_prompt_tokens()
from fractal.matrix import FractalAsyncClient
hs_url = os.environ["MATRIX_HOMESERVER_URL"]
access_token = os.environ["MATRIX_ACCESS_TOKEN"]
client = FractalAsyncClient(hs_url, access_token)
def cleanup():
    print("Your data. Your future.")
    asyncio.run(client.close())
atexit.register(cleanup)
context = {{"c": client, "models": ModelAccessor()}}
config = load_default_config()
config.TerminalInteractiveShell.prompts_class = CustomPrompt
config.TerminalInteractiveShell.banner1 = \"""
Fractal Database Shell

This is a standard IPython shell.
An authenticated Matrix client is available at the local variable `c`.
All Django models are available at the local variable `models`.

The future is in your hands, act accordingly.
\"""
IPython.start_ipython(argv=[], user_ns=context, exec_lines=[], config=config)
"""
        call_command("shell", "--force-color", "-c", init_shell)

    @use_django
    @cli_method
    def create(self, db_name: str, **kwargs):
        """
        Create a database Python module (Django app). Equivalent to `django-admin startapp`.
        ---
        Args:
            db_name: The name of the database to start.

        """
        db_name = db_name.lower()
        print(f"Creating Fractal Database Django app for {db_name}...")
        try:
            os.mkdir(db_name)
        except FileExistsError:
            # get full path to db_name
            full_path = os.path.join(os.getcwd(), db_name)
            print(f"Failed to start app: Directory {full_path} already exists.")
            exit(1)

        os.chdir(db_name)

        import fractal_database

        template_path = os.path.join(fractal_database.__path__[0], "templates", "app_template")  # type: ignore
        call_command("startapp", "--template", template_path, db_name)
        init_poetry_project(db_name)

        from fractal_database.models import Database, Device
        from fractal_database_matrix.models import (
            MatrixCredentials,
            MatrixReplicationTarget,
        )

        current_db = Database.current_db()
        current_db_target: MatrixReplicationTarget = current_db.primary_target()  # type: ignore

        database = Database.objects.create(name=db_name)
        target = MatrixReplicationTarget.objects.create(
            name="matrix",
            database=database,
            homeserver=current_db_target.homeserver,
            primary=True,
        )
        device, _ = Device.objects.get_or_create(
            name=socket.gethostname(), defaults={"name": socket.gethostname()}
        )
        MatrixCredentials.objects.create(
            matrix_id=current_db_target.matrixcredentials.matrix_id,
            access_token=current_db_target.matrixcredentials.access_token,
            target=target,
            device=device,
        )
        database.schedule_replication(created=True, database=database)

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
    def build_base(self, verbose: bool = True):
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
COPY fractal-database-matrix/ /fractal/fractal-database-matrix/
COPY fractal-database/ /fractal/fractal-database/
COPY taskiq-matrix/ /fractal/taskiq-matrix/
COPY fractal-matrix-client/ /fractal/fractal-matrix-client/
COPY fractal-cli/ /fractal/fractal-cli/
RUN pip install /fractal/fractal-cli/
RUN pip install /fractal/fractal-matrix-client/
RUN pip install /fractal/taskiq-matrix/
RUN pip install /fractal/fractal-database-matrix/
RUN pip install /fractal/fractal-database/
"""
        try:
            client = docker.from_env()
        except:
            print("Failed to connect to Docker daemon.")
            print("Is Docker installed and running?")
            exit(1)

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
            pyproject = self._get_fractal_app()

            # detect if it has a namespace property
            if "namespace" in pyproject["tool"]["fractal"]:
                name = f"{pyproject['tool']['fractal']['namespace']}"
        except Exception:
            exit(1)

        try:
            client = docker.from_env()
        except:
            print("Failed to connect to Docker daemon.")
            print("Is Docker installed and running?")
            exit(1)

        name = name.replace("-", "_")
        project_name = name.replace(".", "_")
        image_tag = f"{project_name}:fractal-database"

        # ensure base image is built
        if client.images.list(name=FRACTAL_BASE_IMAGE) == []:
            self.build_base(verbose=verbose)

        dockerfile = f"""
FROM {FRACTAL_BASE_IMAGE}
RUN mkdir /code
COPY . /code
RUN pip install /code

RUN fractal db init --app {name} --project-name {project_name}_app --no-migrate
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
            labels={"database.fractal": "true"},
        )
        for line in response:
            if "stream" in line:
                if verbose:
                    print(line["stream"], end="")
        return image_tag

    @use_django
    @auth_required
    @cli_method
    def publish(self, verbose: bool = True, **kwargs):
        """
        Builds a given database into a Docker container and exports it as a tarball, and
        uploads it to the Fractal Matrix server.

        Must be in the directory where pyproject.toml is located.
        ---
        Args:
            verbose: Whether or not to print verbose output. Defaults to True.

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

        mxc_uri = self.upload(f"{name}.tar", verbose=verbose)

        from fractal_database.models import AppCatalog

        AppCatalog.objects.create(name=name, app_ids=[mxc_uri])

    @auth_required
    @cli_method
    def upload(self, file: str, verbose: bool = True) -> str:
        """
        Builds a given database into a Docker container and exports it as a tarball, and
        uploads it to the Fractal Matrix server.

        Must be in the directory where pyproject.toml is located.
        ---
        Args:
            file: The tarball file to upload.
            verbose: Whether or not to print verbose output (Progress bar).

        """
        try:
            file_size = os.path.getsize(file)
        except FileNotFoundError:
            print(f"Failed to find file {file}.")
            exit(1)

        monitor = None
        if verbose:
            monitor = TransferMonitor(total_size=file_size)
            progress_bar = partial(
                self._print_file_progress,
                file_size=file_size,
                monitor=monitor,
            )
            monitor.on_transferred = progress_bar

        try:
            content_uri = asyncio.run(self._upload_file(file, monitor=monitor))
        except Exception as e:
            print(f"\nFailed to upload file: {e}")
            exit(1)
        except KeyboardInterrupt:
            print("\nCancelled upload.")
            exit(1)

        print(f"Successfully uploaded {file} to {content_uri}")

        return content_uri

    @auth_required
    @cli_method
    def download_file(self, mxc_uri: str, download_path: str = ".", verbose: bool = False):
        """
        Downloads the given app from the Matrix server.
        ---
        Args:
            mxc_uri: The mxc:// URI to download.
            download_path: The path to download the file to. Defaults to current directory.
            verbose: Whether or not to print verbose output (Progress bar).
        """
        # convert mxc_uri to a URL
        http_url = asyncio.run(self._mxc_to_http(mxc_uri))
        if not http_url:
            print(f"Failed to convert {mxc_uri} to an HTTP URL.")
            exit(1)

        res = requests.head(http_url, allow_redirects=True)

        if disposition := res.headers.get("Content-Disposition"):
            file_name = disposition.split("filename=")[1].strip('"')
        else:
            file_name = "app.tar.gz"

        print(f"Downloading {http_url} to {os.path.abspath(download_path)}...")

        command = ["curl", "-o", f"{download_path}/{file_name}"]
        if not verbose:
            command.append("-s")

        try:
            proc = subprocess.run([*command, http_url], check=True)
        except Exception as e:
            print(f"Failed to download {http_url}: {e}")
            exit(1)
        import pdb

        pdb.set_trace()

    @auth_required
    @cli_method
    def download(self, mxc_uri: str, download_path: str = ".", verbose: bool = False):
        """
        Downloads the given app from the Matrix server and loads it into Docker.
        ---
        Args:
            mxc_uri: The mxc:// URI to download.
            download_path: The path to download the file to. Defaults to current directory.
            verbose: Whether or not to print verbose output (Progress bar).
        """
        self.download_file(mxc_uri, download_path, verbose=verbose)

        # load the app into Docker
        try:
            subprocess.run(["docker", "load", "-i", f"{download_path}/app.tar"], check=True)
        except Exception as e:
            print(f"Failed to load app: {e}")
            exit(1)

        # remove the tarball
        os.remove(f"{download_path}/app.tar")

    @use_django
    @auth_required
    @cli_method
    def sync(self, room_id: str, **kwargs):
        """
        Syncs replication tasks from the epoch of a given room.

        ---
        Args:
            room_id: The room ID to sync from.
        """
        os.environ["MATRIX_ROOM_ID"] = room_id
        from fractal_database.replication.tasks import replicate_fixture

        asyncio.run(self._sync_data(room_id))

    @use_django
    @auth_required
    @cli_method
    def fetch(self, **kwargs):
        """
        Fetches latest database info from Matrix for all of your local databases.
        ---
        Args:
        """
        from fractal_database.models import Database
        from fractal_database.replication.tasks import replicate_fixture
        from fractal_database_matrix.models import MatrixReplicationTarget

        databases = Database.objects.all()
        if not databases:
            print("No Databases found. Get started by doing")
            print("fractal init")
        for database in databases:
            primary_target = database.primary_target()
            if isinstance(primary_target, MatrixReplicationTarget):
                room_id: str = primary_target.metadata.get("room_id")
                if room_id:
                    asyncio.run(self._sync_database_metadata(room_id))

    @use_django
    @cli_method
    def list_apps(self):
        """
        Lists all apps installed on this machine.
        ---
        Args:
        """
        from fractal_database.models import Database

        apps = Database.objects.all()
        print(apps)

    list_apps.clicz_aliases = ["ls"]

    @use_django
    @cli_method
    def replicate(self, **kwargs):
        """
        Start a replication process for the configured database.
        ---
        Args:
        """
        call_command("replicate")

    @use_django
    @auth_required
    @cli_method
    def device_create(
        self, name: Optional[str] = None, display_name: Optional[str] = None, **kwargs
    ):
        """
        Creates a new device.
        ---
        Args:
            name: The name of the device to create.
            display_name: Optional display name for the device.
        """
        from fractal_database.models import Device

        if not name:
            name = socket.gethostname()

        d = Device.objects.create(name=name, display_name=display_name)

        matrix_id = d.matrixcredentials_set.get().matrix_id

        print(f"Successfully created and registered device {d.name} as {matrix_id}")

    @use_django
    @auth_required
    @cli_method
    def device_add(self, device_name: str, database_name: str, **kwargs):
        """
        Adds a device to a database.
        ---
        Args:
            device_name: The name of the device to add.
            database_name: The name of the database to add the device to.
        """
        from fractal_database.models import Database, Device

        database = Database.objects.get(name=database_name)
        device = Device.objects.get(name=device_name)
        database.devices.add(device)

        print(f"Successfully added {device.name} to {database.name}")


Controller = FractalDatabaseController
