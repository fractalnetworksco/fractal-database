import pkg_resources

from homeserver.device.clicz import CLICZ


class PluginManager:
    @staticmethod
    def load_plugins(plugin_namespace="fractal_database.plugins"):
        plugins = pkg_resources.iter_entry_points(plugin_namespace)
        loaded_plugins = {}
        for entry_point in plugins:
            loaded_plugins[entry_point.name] = entry_point.load()

        return loaded_plugins


def clicz_entrypoint(clicz: CLICZ):
    for _, plugin_module in PluginManager.load_plugins().items():
        clicz.register_controller(plugin_module.Controller)
