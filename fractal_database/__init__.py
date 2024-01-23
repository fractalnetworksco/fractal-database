from typing import List

import pkg_resources


def autodiscover_apps() -> List[str]:
    """
    Autodiscovers all installed django apps that
    specify a `fractal.database.app` plugin.
    """
    plugins = pkg_resources.iter_entry_points("fractal.database.app")
    apps = [plugin.module_name for plugin in plugins]
    apps.extend(["fractal_database_matrix", "fractal_database"])
    return apps
