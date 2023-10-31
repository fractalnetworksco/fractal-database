import json
import sys
from typing import Any, Dict, List, Optional, Union

from rich.console import Console
from rich.table import Table
from rich.text import Text

KEYS_TO_EXCLUDE = []


def green(text: str) -> Text:
    """
    Renders text as green.

    Args:
        text: Text to render.

    Returns:
        Text rendered as green.
    """
    return Text.assemble((text, "bold green"))


def red(text: str) -> Text:
    """
    Renders text as red.

    Args:
        text: Text to render.

    Returns:
        Text rendered as red.
    """
    return Text.assemble((text, "bold blink red"))


def yellow(text: str) -> Text:
    """
    Renders text as yellow.

    Args:
        text: Text to render.

    Returns:
        Text rendered as yellow.
    """

    return Text.assemble((text, "bold yellow"))


def pretty_bytes(num: float, suffix: str = "B") -> str:
    """
    Converts bytes to human readable format.

    Args:
        num: Bytes to convert.
        suffix: Suffix to append to converted bytes.

    Returns:
        Human readable bytes.
    """
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def render_health(status: str) -> Text:
    """
    Renders health status as a colored string.

    Args:
        status: Health status to render.

    Returns:
        Colored string representing health status.
    """
    if status == "green":
        return green(status)
    elif status == "yellow":
        return yellow(status)
    elif status == "red":
        return red(status)
    else:
        print(f"Got unsupported health color when rendering health: {status}")
        sys.exit(1)


def _pretty_link(link_obj: dict) -> str:
    """
    Extracts link domain from link object.

    Args:
        link_obj: Link object to pretty print.

    Returns:
        Formatted link domain.
    """
    try:
        link_domain = f"https://{link_obj['default']['domain']}"
        return link_domain
    except KeyError:
        print(f"Failed to pretty print link domain")
        sys.exit(1)


def pretty_title(title: str) -> str:
    """
    Replaces underscores with spaces and capitalizes first letter of each word.
    """
    return title.replace("_", " ").title()


def add_titles(table: Table, data: Any, exclude_list: List[str]) -> Table:
    """
    Adds titles to table based on structure of data.

    Args:
        table: Table to add titles to.
        data: Data to use to generate titles.
        exclude_list: List of keys to exclude from display.

    Returns:
        Table with titles added.
    """
    for key in data.keys():
        if key not in exclude_list:
            table.add_column(pretty_title(key), justify="center", overflow="fold")
    return table


def json_to_table(
    title: str,
    data: Union[List[Dict[str, Any]], Dict[str, Any]],
    exclude: List[str] = [],
):
    """
    Pretty prints given data using a table.

    Args:
        title: Title to display above table.
        data: Data to display. Expected as a dictionary or list of dictionaries.
        exclude: List of keys to exclude from display.
    """
    table = Table(title=title)
    exclude_list = [*KEYS_TO_EXCLUDE, *exclude]

    # if given dictionary wrap it in list
    if type(data) == dict:
        table = add_titles(table, data, exclude_list)

    elif type(data) == list and type(data[0]) == dict:
        table = add_titles(table, data[0], exclude_list)

    # wrap object in a list if not already
    if type(data) != list:
        data = [data]

    for row in data:
        col = []
        for key in row.keys():
            if key in exclude_list:
                continue

            if key == "links":
                link_domain = _pretty_link(row[key])
                col.append(link_domain)
            elif key == "health":
                col.append(render_health(row[key]))
            elif "size" in key:
                col.append(pretty_bytes(float(row[key])))
            else:
                col.append(str(row[key]))

        table.add_row(*col, end_section=True)

    c = Console()
    c.print(table)


def print_json(data: Union[List[Dict[str, Any]], Dict[str, Any]], indent: int = 4):
    """
    Prints data as JSON (human readable).
    """
    if indent:
        print(json.dumps(data, indent=indent, default=str))
    else:
        print(json.dumps(data, default=str))


def display(
    data: Union[List[Dict[str, Any]], Dict[str, Any]],
    format: str,
    title: str = "",
    exclude: List[str] = [],
):
    """
    Displays provided data with the specified format

    Args:
        data: Data to display. Expected as a dictionary or list of dictionaries.
        format: Format to display data in. Options are "json" or "pretty".
        title: Title to display above data.
        exclude: List of keys to exclude from display.
    """
    if format == "json":
        print_json(data)
    elif format == "pretty":
        json_to_table(title, data, exclude)
    else:
        json_to_table(title, data, exclude)
