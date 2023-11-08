from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from fractal_database.models import ReplicatedModel, ReplicationTarget


class Representation:
    module = __name__
    repr_method = None

    def get_repr_types(self):
        return [
            base for base in self.__class__.__bases__ if base.__module__.startswith(self.module)
        ]

    @classmethod
    def create_representation_logs(
        cls, instance: "ReplicatedModel", target: "ReplicationTarget", metadata_props: Set[str]
    ):
        """
        Create the representation logs (tasks) for creating a Matrix space
        """
        from fractal_database.models import RepresentationLog

        metadata = {prop: getattr(instance, prop) for prop in metadata_props}

        return [
            RepresentationLog.objects.create(
                instance=instance, method=cls.repr_method, target=target, metadata=metadata
            )
        ]
