from clicz import cli_method


class FractalDatabaseController2:
    """
    Controller that runs when no subcommands are passed.

    Responsible for launching the Homeserver agent's sync loop.
    """

    PLUGIN_NAME = "db2"

    @cli_method
    def run(self):
        """
        Hello World
        ---
        Args:

        """
        print("hello world2")


Controller = FractalDatabaseController2
