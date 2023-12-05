import asyncio

from fractal.cli import cli_method
from fractal.cli.controllers.authenticated import AuthenticatedController
from fractal.matrix import MatrixClient, parse_matrix_id


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

    @cli_method
    def run(self):
        """
        Hello World
        ---
        Args:

        """
        print("hello world")

    @cli_method
    def invite(self, user_id: str, room_id: str, admin: bool = False):
        """
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

    @cli_method
    def join(self, room_id: str):
        """
        Hello World
        ---
        Args:
            room_id: The room ID to join.

        """
        # TODO: When joining fails and the reason is that the user isn't invited,
        # handle knocking on the room
        asyncio.run(self._join_room(room_id))
        print(f"Successfully joined {room_id}")


Controller = FractalDatabaseController
