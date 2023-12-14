from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from fractal_database.models import ReplicatedModel, ReplicationTarget


def get_nested_attr(obj, attr_path):
    """
    Recursively get nested attributes of an object.

    :param obj: The object from which attributes are fetched.
    :param attr_path: String path of nested attributes separated by dots.
    :return: Value of the nested attribute.
    """
    if "." in attr_path:
        head, rest = attr_path.split(".", 1)
        return get_nested_attr(getattr(obj, head), rest)
    else:
        return getattr(obj, attr_path)


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
        cls,
        instance: "ReplicatedModel",
        target: "ReplicationTarget",
        metadata_props: Dict[str, str],
    ):
        """
        Create the representation logs (tasks) for creating a Matrix space
        """
        from fractal_database.models import RepresentationLog

        metadata = {
            prop_name: get_nested_attr(instance, prop)
            for prop_name, prop in metadata_props.items()
        }

        return [
            RepresentationLog.objects.create(
                instance=instance, method=cls.repr_method, target=target, metadata=metadata
            )
        ]
