from sys import exit

from clicz import CLICZ


def main():
    cli = CLICZ(cli_module="fractal_database")
    # cli.default_controller = "fractal"

    cli.dispatch()
    # except Exception as err:
    #     print(f"Error: {err}")
    #     exit(1)
