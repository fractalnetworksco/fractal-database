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

    @classmethod
    def create_representation_logs(
        cls,
        instance: "ReplicatedModel",
        target: "ReplicationTarget",
        metadata: Dict[str, str],
    ):
        """
        Create the representation logs (tasks) for creating a Matrix space
        """
        from fractal_database.models import RepresentationLog

        print("Creating representation log for", cls)
        return [
            RepresentationLog.objects.create(
                instance=instance, method=cls.repr_method, target=target, metadata=metadata
            )
        ]
