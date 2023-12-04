from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from fractal_database.models import ReplicatedModel, ReplicationTarget


class Representation:
    module = __name__
    repr_method = None

    def get_repr_types(self):
        """
        Wacky inheritance introspection stuff lies ahead.

        Fractal Database ReplicatedModels that want an external representation must directly
        subclass this class or one of its subclasses.

        This method looks its parent and returns any classes from the module
        of the class that inherits from this class.

        Classes must directly subclass this class to be considered for a representation.

        For example:

        class MyModel(Representation):
            pass

        class MyModelSubclass(MyModel): # this wont work
            pass

        instead do this:

        class MyModelSubclass(MyModel, Representation): # this will work
            pass
        """
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

        # comment me
        metadata = {prop: getattr(instance, prop) for prop in metadata_props}

        return [
            RepresentationLog.objects.create(
                instance=instance, method=cls.repr_method, target=target, metadata=metadata
            )
        ]
