import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fractal_database.models import AppInstanceConfig

logger = logging.getLogger(__name__)


def launch_app(app_config: "AppInstanceConfig", *args, **kwargs) -> None:
    """ """
    logger.info("Launching app %s with config %s", app_config.app.name, app_config)


def stop_app(app_config: "AppInstanceConfig", *args, **kwargs) -> None:
    """ """
    logger.info("Stopping app %s with config %s", app_config.app.name, app_config)
