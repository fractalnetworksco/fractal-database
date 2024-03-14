from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fractal_database.models import ReplicatedModel, ReplicationTarget


class StaleObjectException(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(
            "Object version was updated by another process. Reload object and try again."
        )


class ReplicatedInstanceConfigAlreadyExists(Exception):
    def __init__(self, instance: "ReplicatedModel", target: "ReplicationTarget", *args, **kwargs):
        self.msg = f"ReplicatedModel {instance} is already being replicated to {target}"
        super().__init__(self.msg)
